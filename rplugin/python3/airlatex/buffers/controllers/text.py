from airlatex.lib.range import FenwickTree, NaiveAccumulator
from airlatex.lib.task import AsyncDecorator, Task

from difflib import SequenceMatcher
from hashlib import sha1

from copy import deepcopy


class Text():

  def __init__(self):
    self.previous = []
    self.lines = NaiveAccumulator()

  @property
  def content_hash(self):
    # compute sha1-hash of current buffer
    # compute sha1-hash of current buffer
    buffer_cpy = self.previous[:]
    current_len = 0
    for i, row in enumerate(buffer_cpy):
      current_len += len(row) + 1
    current_len -= 1
    tohash = ("blob " + str(current_len) + "\x00")
    # self.log.debug(f"Lengths {current_len, self.lines[-1]}")

    tohash = ("blob " + str(current_len) + "\x00") + "\n".join(buffer_cpy)
    sha = sha1()
    sha.update(tohash.encode())
    return sha.hexdigest()

  def query(self, start, end):
    start_line, start_col = self.lines.search(start)
    end_line, end_col = self.lines.search(end)
    return start_line, start_col, end_line, end_col

  def updateBuffer(self, buffer):
    self.previous = buffer[:]

  def write(self, buffer, lines):
    buffer[:] = []
    if lines:
      buffer[0] = lines[0]
      lengths = [
          0,
      ] * len(lines)
      lengths[0] = len(lines[0]) + 1
      for i, l in enumerate(lines[1:]):
        buffer.append(l)
        lengths[i + 1] = len(l) + 1
      # No new line on last line
      lengths[-1] -= 1
    else:
      lengths = [0]
    self.lines.initialize(lengths)
    self.updateBuffer(buffer)

  def buildOps(self, buffer):
    # skip if not yet initialized
    if self.previous is None:
      return []

    # nothing to do
    if len(self.previous) == len(buffer):
      skip = True
      for ol, nl in zip(self.previous, buffer):
        if hash(ol) != hash(nl):
          skip = False
          break
      if skip:
        # self.log.debug("writeBuffer: -> done (hashtest says nothing to do)")
        return []

    # cumulative position of line
    pos = deepcopy(self.lines)

    # first calculate diff row-wise
    ops = []
    S = SequenceMatcher(
        None, self.previous, buffer, autojunk=False).get_opcodes()
    for op in S:
      if op[0] == "equal":
        continue

      # inserting a whole row
      elif op[0] == "insert":
        # self.log.debug(f"Insert")
        selection = buffer[op[3]:op[4]]
        s = "\n".join(selection)
        for l in selection[::-1]:
          if op[3] == self.lines.last_index:
            if op[3]:
              self.lines[op[3] - 1] += 1
            self.lines.insert(op[3], len(l))
          else:
            self.lines.insert(op[3], len(l) + 1)
        if op[1] >= len(self.previous):
          p = pos[-1] - 1
          s = "\n" + s
        else:
          p = pos[op[1]]
          s = s + "\n"
        ops.append({"p": p, "i": s})

      # deleting a whole row
      elif op[0] == "delete":
        # self.log.debug(f"Delete")
        s = "\n".join(self.previous[op[1]:op[2]])
        for i in range(op[1], op[2]):
          del self.lines[op[3]]
          # If last line previous line needs to remove new line char
          if op[3] and op[3] == self.lines.last_index:
            self.lines[op[3] - 1] -= 1
        if op[1] == len(buffer):
          p = pos[-(op[2] - op[1]) - 1] - 1
          s = "\n" + s
        else:
          p = pos[op[1]]
          s = s + "\n"
        ops.append({"p": p, "d": s})

      # for replace, check in more detail what has changed
      elif op[0] == "replace":
        # self.log.debug(f"replace")
        old = "\n".join(self.previous[op[1]:op[2]])
        selection = buffer[op[3]:op[4]]
        new = "\n".join(selection)
        # Since Sequence Matcher works in order, we need to use the indices on
        # the buffer.
        for i, s in zip(range(op[3], op[4]), selection):
          # Account for new lines at end of document
          if i == self.lines.last_index:
            self.lines[i] = len(s)
          else:
            self.lines[i] = len(s) + 1

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
      # self.log.debug(
      #     "writeBuffer: -> done (sequencematcher says nothing to do)")
      return []

    # update saved buffer & send command
    self.previous = buffer

    # reverse, as last op should be applied first
    ops.reverse()
    return ops

  def applyOp(self, buffer, op):
    # delete char and lines
    if 'd' in op:
      p = op['p']
      s = op['d']
      self._remove(buffer, p, s)

    # add characters and newlines
    if 'i' in op:
      p = op['p']
      s = op['i']
      self._insert(buffer, p, s)

    # add comment
    if 'c' in op:
      thread = {"id": op['t'], "metadata": packet["meta"], "op": op}
      self.threads[op['t']] = thread

  # inster string at given position
  def _insert(self, buffer, start, string):
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
