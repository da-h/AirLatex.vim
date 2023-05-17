import pynvim
from difflib import SequenceMatcher
from hashlib import sha1
import asyncio
from asyncio import create_task, Lock
from logging import getLogger
import time

from intervaltree import Interval, IntervalTree
from airlatex.range import FenwickTree, NaiveAccumulator

from copy import deepcopy

import hashlib

if "allBuffers" not in globals():
  allBuffers = {}


class DocumentBuffer:
  allBuffers = allBuffers

  def __init__(self, path, nvim):
    self.comments_active = True
    self.comments_display = True
    self.nonce = f"{time.time()}"
    self.log = getLogger("AirLatex")
    self.path = path
    self.nvim = nvim
    self.project_handler = path[0]["handler"]
    self.document = path[-1]
    self.saved_buffer = None
    self.threads = {}
    self.highlight = self.nvim.api.create_namespace('AirLatexCommentGroup')
    self.highlight2 = self.nvim.api.create_namespace(
        'AirLatexDoubleCommentGroup')
    self.pending_selection = self.nvim.api.create_namespace(
        'PendingCommentGroup')
    self.comment_selection = IntervalTree()
    self.thread_intervals = IntervalTree()
    self.buffer_event = asyncio.Event()
    self.cursors = {}
    self.buffer_mutex = Lock()
    self.initDocumentBuffer()
    # self.cumulative_lines = FenwickTree()
    self.cumulative_lines = NaiveAccumulator()

  def command(self, cmd):
    for c in cmd.split("\n"):
      self.nvim.command(c.strip())

  @staticmethod
  def getName(path):
    return "/".join([p["name"] for p in path])

  @staticmethod
  def getExt(document):
    return document["name"].split(".")[-1]

  def buildContentHash(self, cumulative_lines=None):
    # compute sha1-hash of current buffer
    buffer_cpy = self.buffer[:]
    current_len = 0
    for row in buffer_cpy:
      current_len += len(row) + 1
    current_len -= 1
    tohash = ("blob " + str(current_len) + "\x00")
    for b in buffer_cpy[:-1]:
      tohash += b + "\n"
    tohash += buffer_cpy[-1]
    hash2 = tohash
    tohash = ("blob " + str(current_len) + "\x00") + "\n".join(buffer_cpy)
    sha_ = sha1()
    sha_.update(tohash.encode())

    sha = sha1()
    sha.update(hash2.encode())
    r = sha.hexdigest()
    self.log.debug(f"{r, sha_.hexdigest()}")
    return r

    if cumulative_lines == None:
      cumulative_lines = self.cumulative_lines
    # compute sha1-hash of current buffer
    buffer_cpy = self.buffer[:]
    current_len = 0
    for i, row in enumerate(buffer_cpy):
      self.log.debug(f"{current_len, self.cumulative_lines[i]}")
      current_len += len(row) + 1
    current_len -= 1
    tohash = ("blob " + str(current_len) + "\x00")
    self.log.debug(f"{current_len, self.cumulative_lines[-1]}")

    # current_len = self.cumulative_lines[-1]
    tohash = ("blob " + str(current_len) + "\x00") + "\n".join(buffer_cpy)
    self.log.debug(hash2)
    self.log.debug(tohash)
    sha = sha1()
    sha.update(hash2.encode())
    return sha.hexdigest()

  @property
  def name(self):
    return DocumentBuffer.getName(self.path)

  @property
  def ext(self):
    return DocumentBuffer.getExt(self.document)

  @property
  def augroup(self):
    "Need a file unique string. Could use docid I guess."
    return hashlib.md5((self.name + self.nonce).encode('utf-8')).hexdigest()

  async def deactivate(self):
    await self.buffer_mutex.acquire()
    if self.buffer not in DocumentBuffer.allBuffers:
      self.buffer_mutex.release()
      return
    del DocumentBuffer.allBuffers[self.buffer]
    def callback():
      try:
        buffer = self.nvim.current.buffer
        self.buffer.api.clear_namespace(self.highlight, 0, -1)
        self.buffer.api.clear_namespace(self.highlight2, 0, -1)
        self.buffer.options.syntax = False
        self.nvim.command(f"autocmd! {self.augroup}")
        # Changing the name breaks vimtex.
        try:
          self.buffer.name = f"Offline {self.augroup}"
        except:
          pass
        self.thread_intervals.clear()
      finally:
        self.buffer_mutex.release()
    self.nvim.async_call(callback)

  def initDocumentBuffer(self):

    # Creating new Buffer
    self.nvim.command(f"""
      wincmd w
      enew
      file {self.name}
    """)

    self.buffer = self.nvim.current.buffer
    DocumentBuffer.allBuffers[self.buffer] = self

    # Buffer Settings
    self.nvim.command(f"""
      syntax on
      setlocal noswapfile
      setlocal buftype=nofile
      set filetype={self.ext}
    """)

    # Autogroups
    self.nvim.command(f"""
    augroup {self.augroup}
      au CursorMoved <buffer> call AirLatex_MoveCursor()
      au CursorMovedI <buffer> call AirLatex_WriteBuffer()
      command! -buffer -nargs=0 W call AirLatex_WriteBuffer()
    augroup END
    """)
    # au CursorMoved <buffer> call AirLatex_ShowComments()

    # Buffer bindings
    self.nvim.command(f"""
      vnoremap gv :<C-u>call AirLatex_CommentSelection()<CR>
      cmap <buffer> w call AirLatex_GitSync(input('Commit Message: '))<CR>
      " Alternatively
      " cmap <buffer> w call AirLatex_Compile()<CR>
    """)

    # Comment formatting
    self.nvim.command(f"""
      hi PendingCommentGroup ctermbg=190
      hi AirLatexCommentGroup ctermbg=58
      hi AirLatexDoubleCommentGroup ctermbg=94
      hi CursorGroup ctermbg=18
    """)

  def syncGit(self, message=None):
    while not message:
      message = self.nvim.funcs.input('Commit Message: ')
    create_task(self.project_handler.syncGit(message))

  def compile(self):
    create_task(self.project_handler.compile())

  def highlightRange(
      self, highlight, group, start_line, start_col, end_line, end_col):
    if start_line == end_line:
      self.buffer.api.add_highlight(
          highlight, group, start_line, start_col, end_col)
    else:
      self.buffer.api.add_highlight(highlight, group, start_line, start_col, -1)
      for line_num in range(start_line + 1, end_line):  # In-between lines
        self.buffer.api.add_highlight(highlight, group, line_num, 0, -1)
      self.buffer.api.add_highlight(highlight, group, end_line, 0, end_col)

  def markComment(self, *lineinfo):
    if self.comment_selection.is_empty():
      self.comment_selection = IntervalTree()
      start_line, start_col, end_line, end_col = lineinfo
      self.comment_selection.add(
          Interval(
              self.cumulative_lines.position(start_line, start_col),
              self.cumulative_lines.position(end_line, end_col)))

      self.highlightRange(
          self.pending_selection, "PendingCommentGroup", *lineinfo)

  def getCommentPosition(self, next: bool = False, prev: bool = False):
    if next == prev:
      return (-1, -1), 0

    cursor = self.nvim.current.window.cursor
    cursor_offset = self.cumulative_lines.position(cursor[0] - 1, cursor[1])

    if next:
      positions = self.thread_intervals[
          cursor_offset + 1:] - self.thread_intervals[cursor_offset]
      offset = len(self.thread_intervals[:]) - len(positions) + 1
      if not positions:
        positions = self.thread_intervals[:
                                          cursor_offset] - self.thread_intervals[
                                              cursor_offset]
        offset = 1
      if not positions:
        return (-1, -1), 0
      pos = min(positions).begin
    elif prev:
      positions = self.thread_intervals[:cursor_offset] - self.thread_intervals[
          cursor_offset]
      offset = len(positions)
      if not positions:
        positions = self.thread_intervals[
            cursor_offset + 1:] - self.thread_intervals[cursor_offset]
        offset = 1
      if not positions:
        return (-1, -1), 0
      pos = max(positions).begin

    _, start_line, start_col, *_ = self.getLineInfo(pos, pos + 1)
    return (start_line + 1, start_col), offset

  def publishComment(self, thread, count, content):

    def callback():
      self.log.debug(f"Calling {content, thread, count}")
      create_task(
          self.project_handler.sendOps(
              self.document,
              self.content_hash,
              ops=[{
                  "c": content,
                  "p": count,
                  "t": thread
              }]))

    self.nvim.async_call(callback)

  def highlightComment(self, comments, thread):
    thread_id = thread["id"]
    comments = comments.get(thread_id, {})
    resolved = comments.get("resolved", False)
    if resolved or not comments:
      return

    start = thread["op"]["p"]
    end = start + len(thread["op"]["c"])

    char_count, start_line, start_col, end_line, end_col = self.getLineInfo(
        start, end)
    # Apply the highlight
    self.log.debug(f"highlight {start_line} {start_col} {end_line} {end_col}")

    if start == end:
      start -= 1
      end += 1
      start_col = max(start_col - 1, 0)
      end_col = min(
          end_col + 1, char_count + self.cumulative_lines[end_line] - 1)

    self.highlightRange(
        self.highlight, 'AirLatexCommentGroup', start_line, start_col, end_line,
        end_col)
    self.thread_intervals[start:end] = thread_id

  async def highlightComments(self, comments, threads=None):
    # Clear any existing highlights

    def highlight_callback():
      self.buffer.api.clear_namespace(self.highlight, 0, -1)
      self.buffer.api.clear_namespace(self.highlight2, 0, -1)
      self.thread_intervals.clear()
      if threads:
        self.threads = {thread["id"]: thread for thread in threads}
      for thread in self.threads.values():
        self.highlightComment(comments, thread)
      # Apply double highlights. Note we could extend this to the nth case, but
      # 2 seems fine
      overlapping_ranges = set()
      for interval in self.thread_intervals:
        overlaps = self.thread_intervals[interval.begin:interval.end]
        for overlap in overlaps:
          if overlap == interval:
            continue
          overlapping_range = Interval(
              max(interval.begin, overlap.begin),
              min(interval.end, overlap.end))
          overlapping_ranges.add(overlapping_range)
      for overlap in overlapping_ranges:
        _, *lineinfo = self.getLineInfo(overlap.begin, overlap.end)
        self.highlightRange(
            self.highlight2, 'AirLatexDoubleCommentGroup', *lineinfo)

    await self.buffer_event.wait()
    self.nvim.async_call(highlight_callback)

  async def showComments(self, cursor, comment_buffer):
    previous_state = self.comments_active
    self.comments_display = not (comment_buffer.drafting or
                                comment_buffer.creation)
    if not self.comments_display:
      return
    if not previous_state:
      self.nvim.async_call(self.buffer.api.clear_namespace, self.pending_selection, 0, -1)
      self.comment_selection = IntervalTree()

    cursor_offset = self.cumulative_lines.position(cursor[0] - 1, cursor[1])
    self.log.debug(f"Show comments {cursor}, {cursor_offset}, {[t for t in self.thread_intervals]}")
    self.log.debug(f"Sanity {[self.cumulative_lines[i] for i in range(cursor[0])]} {self.cumulative_lines.arr} ")

    threads = self.thread_intervals[cursor_offset]

    previously_active = self.comments_active
    self.comments_active = bool(threads)
    if not self.comments_active:
      if previously_active:
        comment_buffer.clear()
      return
    self.log.debug(f"found threads {threads}")
    comment_buffer.render(self.project_handler, threads)

  def clearRemoteCursor(self, remote_id):
    if remote_id in self.cursors:
      highlight = self.cursors[remote_id]
      self.buffer.api.clear_namespace(highlight, 0, -1)

  def updateRemoteCursor(self, cursor):
    self.log.debug(f"updateRemoteCursor {cursor}")
    # Don't draw the current cursor
    # Client id if remote, id if local
    if not cursor.get("id") or cursor.get(
        "id") == self.project_handler.session_id:
      return

    def handle_cursor(cursor):
      if cursor["id"] not in self.cursors:
        highlight = self.nvim.api.create_namespace(cursor["id"])
        self.cursors[cursor["id"]] = highlight
      else:
        highlight = self.cursors[cursor["id"]]
        self.buffer.api.clear_namespace(highlight, 0, -1)
      self.log.debug(
          f"highlighting {cursor} 'CursorGroup', {(cursor['row'], cursor['column'], cursor['column'])}"
      )
      if len(self.buffer[cursor["row"]]) == cursor["column"]:
        self.buffer.api.add_highlight(
            highlight, 'CursorGroup', cursor["row"],
            max(cursor["column"] - 1, 0), cursor["column"])
      else:
        self.buffer.api.add_highlight(
            highlight, 'CursorGroup', cursor["row"], cursor["column"],
            cursor["column"] + 1)

    self.nvim.async_call(handle_cursor, cursor)

  def getLineInfo(self, start, end):
    char_count, start_line, start_col, end_line, end_col = 0, -1, 0, 0, 0
    # TODO replace with search
    for i, line in enumerate(self.buffer[:]):
      line_length = len(line) + 1  # +1 for the newline character
      if char_count + line_length > start and start_line == -1:
        start_line, start_col = i, start - char_count
      if char_count + line_length >= end:
        end_line, end_col = i, end - char_count
        break
      char_count += line_length
    return char_count, start_line, start_col, end_line, end_col

  def write(self, lines):

    def writeLines(buffer, lines):
      buffer[0] = lines[0]
      self.cumulative_lines[0] = 0
      self.cumulative_lines[1] = len(lines[0]) + 1
      for i, l in enumerate(lines[1:]):
        buffer.append(l)
        self.cumulative_lines[i + 2] = len(l) + 1
      self.saved_buffer = buffer[:]
      self.buffer_event.set()

    self.nvim.async_call(writeLines, self.buffer, lines)

  def writeBuffer(self, comments=None):
    self.log.debug("writeBuffer: calculating changes to send")

    # update CursorPosition
    cursor = self.nvim.current.window.cursor
    create_task(
        self.project_handler.updateCursor(
            self.document, cursor))

    if comments:
      create_task(self.showComments(cursor, comments))

    # skip if not yet initialized
    if self.saved_buffer is None:
      self.log.debug("writeBuffer: -> buffer not yet initialized")
      return

    buffer = self.buffer[:]

    # nothing to do
    if len(self.saved_buffer) == len(buffer):
      skip = True
      for ol, nl in zip(self.saved_buffer, buffer):
        if hash(ol) != hash(nl):
          skip = False
          break
      if skip:
        self.log.debug("writeBuffer: -> done (hashtest says nothing to do)")
        return

    # cumulative position of line
    pos = deepcopy(self.cumulative_lines)

    # first calculate diff row-wise
    ops = []
    S = SequenceMatcher(
        None, self.saved_buffer, buffer, autojunk=False).get_opcodes()
    for op in S:
      if op[0] == "equal":
        continue

      # inserting a whole row
      elif op[0] == "insert":
        selection = buffer[op[3]:op[4]]
        s = "\n".join(selection)
        for l in selection[::-1]:
          self.log.debug(f"FFF {selection, len(l)}")
          self.cumulative_lines.insert(op[3], len(l) + 1)
        if op[1] >= len(self.saved_buffer):
          p = pos[-1] - 1
          s = "\n" + s
        else:
          p = pos[op[1]]
          s = s + "\n"
        ops.append({"p": p, "i": s})

      # deleting a whole row
      elif op[0] == "delete":
        self.log.debug(f"Delete")
        s = "\n".join(self.saved_buffer[op[1]:op[2]])
        for i in range(op[1], op[2]):
          del self.cumulative_lines[op[3]]
        if op[1] == len(buffer):
          p = pos[-(op[2] - op[1]) - 1] - 1
          s = "\n" + s
        else:
          p = pos[op[1]]
          s = s + "\n"
        ops.append({"p": p, "d": s})

      # for replace, check in more detail what has changed
      elif op[0] == "replace":
        self.log.debug(f"replace")
        old = "\n".join(self.saved_buffer[op[1]:op[2]])
        selection  = buffer[op[3]:op[4]]
        new = "\n".join(selection)
        # Since Sequence Matcher works in order, we need to use the indices on
        # the buffer.
        for i, s in zip(range(op[3], op[4]), selection):
          self.cumulative_lines[i] = len(s) + 1

        S2 = SequenceMatcher(None, old, new, autojunk=False).get_opcodes()
        for op2 in S2:
          # relative to document end
          linestart = pos[op[1]]

          if op2[0] == "equal":
            continue

          elif op2[0] == "replace":
            ops.append({"p": linestart + op2[1], "i": new[op2[3]:op2[4]]})
            ops.append({"p": linestart + op2[1], "d": old[op2[1]:op2[2]]})

          elif op2[0] == "insert":
            ops.append({"p": linestart + op2[1], "i": new[op2[3]:op2[4]]})

          elif op2[0] == "delete":
            ops.append({"p": linestart + op2[1], "d": old[op2[1]:op2[2]]})

    # nothing to do
    if len(ops) == 0:
      self.log.debug(
          "writeBuffer: -> done (sequencematcher says nothing to do)")
      return

    # reverse, as last op should be applied first
    ops.reverse()

    # update saved buffer & send command
    self.saved_buffer = buffer
    self.log.debug(" -> sending ops")

    track = self.nvim.eval("g:AirLatexTrackChanges") == 1
    create_task(
        self.project_handler.sendOps(
            self.document, self.buildContentHash(), ops, track))

  def applyUpdate(self, packet, comments):
    self.log.debug("apply server updates to buffer")

    # adapt version
    if "v" in packet:
      v = packet["v"]
      if v >= self.document["version"]:
        self.document["version"] = v + 1

    # do nothing if no op included
    if not 'op' in packet:
      return
    ops = packet['op']

    # async execution
    def applyOps(self, ops):
      self.buffer_mutex.acquire()
      try:
        for op in ops:
          self.log.debug(f"the op {op} and {'c' in op}")

          # delete char and lines
          if 'd' in op:
            p = op['p']
            s = op['d']
            self._remove(self.saved_buffer, p, s)
            self._remove(self.buffer, p, s)

          # add characters and newlines
          if 'i' in op:
            p = op['p']
            s = op['i']
            self._insert(self.saved_buffer, p, s)
            self._insert(self.buffer, p, s)

          # add comment
          if 'c' in op:
            thread = {"id": op['t'], "metadata": packet["meta"], "op": op}
            self.threads[op['t']] = thread
            create_task(self.highlightComments(comments))
      except Exception as e:
        self.log.debug(f"{op} failed: {e}")
      finally:
        self.buffer_mutex.release()

    self.nvim.async_call(applyOps, self, ops)

  # inster string at given position
  def _insert(self, buffer, start, string):
    p_linestart = 0

    # find start line
    # TODO replace with search
    for line_i, line in enumerate(self.buffer):

      # start is not yet there
      if start >= p_linestart + len(line) + 1:
        p_linestart += len(line) + 1
      else:
        break

    # convert format to array-style
    string = string.split("\n")

    # append end of current line to last line of new line
    string[-1] += line[(start - p_linestart):]

    # include string at start position
    buffer[line_i] = line[:(start - p_linestart)] + string[0]

    # append rest to next line
    if len(string) > 1:
      buffer[line_i + 1:line_i + 1] = string[1:]

  # remove len chars from pos
  def _remove(self, buffer, start, string):
    p_linestart = 0

    # find start line
    # TODO replace with search
    for line_i, line in enumerate(buffer):

      # start is not yet there
      if start >= p_linestart + len(line) + 1:
        p_linestart += len(line) + 1
      else:
        break

    # convert format to array-style
    string = string.split("\n")
    new_string = ""

    # remove first line from found position
    new_string = line[:(start - p_linestart)]

    # add rest of last line to new string
    if len(string) == 1:
      new_string += buffer[line_i + len(string) - 1][(start - p_linestart) +
                                                     len(string[-1]):]
    else:
      new_string += buffer[line_i + len(string) - 1][len(string[-1]):]

    # overwrite buffer
    buffer[line_i:line_i + len(string)] = [new_string]
