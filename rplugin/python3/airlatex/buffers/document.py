from collections import namedtuple
from copy import deepcopy
from difflib import SequenceMatcher
from hashlib import sha1, md5
import time
import asyncio

from intervaltree import Interval, IntervalTree

from airlatex.lib.task import AsyncDecorator, Task
from airlatex.buffers.buffer import Buffer
from airlatex.buffers.controllers.text import Text
from airlatex.buffers.controllers.thread import Threads

if "allBuffers" not in globals():
  allBuffers = {}

highlight_groups = [
    'AirLatexCommentGroup', 'AirLatexDoubleCommentGroup', 'PendingCommentGroup'
]
highlight = namedtuple("Highlight", ["comment", "double", "pending"])

# TODO:
# Ok then
# - document fix up
#   - Fenwick tree
#   - Interval updates


class Document(Buffer):
  allBuffers = allBuffers

  def __init__(self, nvim, project, path, data, new_buffer=True):
    self.data = data
    self.name = Document.getName(path, project.data)
    self.ext = Document.getExt(self.data)
    self.nonce = f"{time.time()}"
    self.project = project
    self.highlight_names = highlight(*highlight_groups)
    super().__init__(nvim, new_buffer=new_buffer)

    self.buffer_event = asyncio.Event()
    self.data["ops_buffer"] = []
    self.cursors = {}
    self.highlight = highlight(
        *map(self.nvim.api.create_namespace, highlight_groups))

    self.text = Text()
    self.threads = Threads()

  def buildBuffer(self, new_buffer=True):

    if new_buffer:
      self.nvim.command(
          f"""
        wincmd w
        enew
        file {self.name}
      """)
    else:
      # Reuse the current buffer
      self.nvim.command(f"file {self.name}")

    buffer = self.nvim.current.buffer
    Document.allBuffers[buffer] = self

    # Buffer Settings
    self.command(
        f"""
      syntax on
      setlocal noswapfile
      setlocal buftype=nofile
      set filetype={self.ext}
      setlocal modifiable
    """)

    # Autogroups
    self.command(
        f"""
    augroup {self.augroup}
      au CursorMoved <buffer> call AirLatex_MoveCursor()
      au CursorMovedI <buffer> call AirLatex_WriteBuffer()
      command! -buffer -nargs=0 W call AirLatex_WriteBuffer()
    augroup END
    """)
    # au CursorMoved <buffer> call AirLatex_ShowComments()

    # Buffer bindings
    pid = self.project.id
    did = self.id
    self.command(
        f"""
      vnoremap gv :<C-u>call AirLatex_CommentSelection()<CR>
      nnoremap <buffer> R :call AirLatex_Refresh('{pid}', '{did}')<enter>
      cmap <buffer> w call AirLatex_GitSync(input('Commit Message: '))<CR>
      " Alternatively
      " cmap <buffer> w call AirLatex_Compile()<CR>
    """)

    # Comment formatting
    self.command(
        f"""
      hi {self.highlight_names.pending} ctermbg=190
      hi {self.highlight_names.comment} ctermbg=58
      hi {self.highlight_names.double} ctermbg=94
      hi CursorGroup ctermbg=18
    """)
    return buffer

  @property
  def id(self):
    return self.data["_id"]

  @property
  def version(self):
    return self.data["version"]

  @version.setter
  def version(self, v):
    self.data["version"] = v

  @staticmethod
  def getName(path, project_data):
    return "/".join([project_data["name"]] + [p["name"] for p in path[1:]])

  @staticmethod
  def getExt(document):
    return document["name"].split(".")[-1]

  @property
  def augroup(self):
    "Need a file unique string. Could use docid I guess."
    return "x" + md5((self.name + self.nonce).encode('utf-8')).hexdigest()

  async def deactivate(self):
    await self.lock.acquire()
    if self.buffer not in Document.allBuffers:
      return
    del Document.allBuffers[self.buffer]

    @Task.Fn(vim=True)
    def callback():
      # Changing the name breaks vimtex.
      try:
        self.buffer.name = f"Offline {self.augroup}"
      except:
        pass

      try:
        buffer = self.nvim.current.buffer
        self.buffer.api.clear_namespace(self.highlight.comment, 0, -1)
        self.buffer.api.clear_namespace(self.highlight.double, 0, -1)
        # Turn off syntax to emphasize we are offline
        # Delete key bindings
        # Add new keybinding to refresh
        self.command(
            f"""
          buffer {self.buffer.number}
          autocmd! {self.augroup}
          set syntax=off
          buffer {buffer.number}
        """)
        self.threads.clear()
      finally:
        self.lock.release()

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
    if self.threads.selection.is_empty():
      self.threads.select(self.text, *lineinfo)
      self.highlightRange(
          self.highlight.pending, self.highlight_names.pending, *lineinfo)

  def getCommentPosition(self, next=False, prev=False):
    if next == prev:
      return (-1, -1), 0
    cursor = self.nvim.current.window.cursor
    cursor_offset = self.text.lines.position(cursor[0] - 1, cursor[1])
    if next:
      pos, offset = self.threads.getNextPosition(cursor_offset)
    else:
      pos, offset = self.threads.getPrevPosition(cursor_offset)
    self.log.debug(f"TRY NEXT {pos, offset}")
    if offset == 0:
      return (-1, -1), 0
    line, col, *_ = self.text.query(pos, pos + 1)
    return (line + 1, col), offset

  @AsyncDecorator
  def publishComment(self, thread, count, content):
    # Yes, we call document, just to call back because we need to get buffer info.
    return self.project.sendOps(
        self.id,
        self.text.content_hash,
        ops=[{
            "c": content,
            "p": count,
            "t": thread
        }])

  def highlightComment(self, comments, thread):
    created, lineinfo = self.threads.create(self.text, comments, thread)
    if created:
      self.highlightRange(
          self.highlight.comment, self.highlight_names.comment, *lineinfo)

  async def highlightComments(self, comments, threads=None):
    @Task(self.buffer_event.wait).fn(vim=True)
    def highlight_callback():
      # Clear any existing highlights
      self.buffer.api.clear_namespace(self.highlight.comment, 0, -1)
      self.buffer.api.clear_namespace(self.highlight.double, 0, -1)
      self.threads.clear()
      if threads:
        self.threads.data = {thread["id"]: thread for thread in threads}
      for thread in self.threads.data.values():
        self.highlightComment(comments, thread)
      # Apply double highlights. Note we could extend this to the nth case, but
      # 2 seems fine
      for overlap in self.threads.doubled:
        lineinfo = self.text.query(overlap.begin, overlap.end)
        self.highlightRange(
            self.highlight.double, self.highlight_names.double, *lineinfo)

  async def showComments(self, cursor, comment_buffer):
    if comment_buffer.drafting or comment_buffer.creation:
      return

    active = self.threads.active
    threads = self.threads.activate(self.text, cursor)
    if not active:
      Task(
          self.buffer.api.clear_namespace,
          self.highlight.pending,
          0,
          -1,
          vim=True)
      self.threads.selection.clear()
      if not threads:
        return
    elif not threads:
      comment_buffer.clear()
      return
    comment_buffer.render(self.project, threads)

  def clearRemoteCursor(self, remote_id):
    @Task.Fn(remote_id, vim=True)
    def clear_cursor(remote_id):
      if remote_id in self.cursors:
        highlight = self.cursors[remote_id]
        self.buffer.api.clear_namespace(highlight, 0, -1)

  def updateRemoteCursor(self, cursor):
    # Don't draw the current cursor
    # Client id if remote, id if local
    if not cursor.get("id") or cursor.get("id") == self.project.session_id:
      return

    @Task.Fn(cursor, vim=True)
    def handle_cursor(cursor):
      buffer = self.buffer[:]
      if cursor["id"] not in self.cursors:
        highlight = self.nvim.api.create_namespace(cursor["id"])
        self.cursors[cursor["id"]] = highlight
      else:
        highlight = self.cursors[cursor["id"]]
        self.buffer.api.clear_namespace(highlight, 0, -1)
      # Handle case that cursor is at end of line
      # Guard against being on the last line
      row = min(cursor["row"], len(buffer) - 1)
      if len(buffer[row]) == cursor["column"]:
        self.buffer.api.add_highlight(
            highlight, 'CursorGroup', cursor["row"],
            max(cursor["column"] - 1, 0), cursor["column"])
      else:
        self.buffer.api.add_highlight(
            highlight, 'CursorGroup', cursor["row"], cursor["column"],
            cursor["column"] + 1)

  def write(self, lines):
    @Task(self.lock.acquire).fn(self.buffer, lines, vim=True)
    def _write(buffer, lines):
      self.text.write(buffer, lines)
      self.lock.release()
      self.buffer_event.set()

  def broadcastUpdates(self, comments=None):
    self.log.debug("writeBuffer: calculating changes to send")
    if not self.buffer_event.is_set():
      return

    # update CursorPosition
    cursor = self.nvim.current.window.cursor
    Task(self.project.updateCursor(self.data, cursor))
    if comments:
      Task(self.showComments(cursor, comments))

    ops = self.text.buildOps(self.buffer[:])
    if not ops:
      return

    track = self.nvim.eval("g:AirLatexTrackChanges") == 1
    Task(self.project.sendOps(self.id, self.text.content_hash, ops, track))

  def applyUpdate(self, packet, comments):
    self.log.debug("apply server updates to buffer")

    # adapt version
    if "v" in packet:
      v = packet["v"]
      if v >= self.version:
        self.version = v + 1

    # do nothing if no op included
    if not 'op' in packet:
      return
    ops = packet['op']

    # async execution
    @Task(self.lock.acquire).fn(self, ops, vim=True)
    def applyOps(self, ops):
      try:
        for op in ops:
          self.log.debug(f"the op {op} and {'c' in op}")
          self.text.applyOp(self.buffer, op)
          # add comment
          if 'c' in op:
            thread = {"id": op['t'], "metadata": packet["meta"], "op": op}
            self.threads.data[op['t']] = thread
            Task(self.highlightComments(comments))

        self.text.updateBuffer(self.buffer[:])
      except Exception as e:
        self.log.debug(f"{op} failed: {e}")
      finally:
        self.lock.release()
