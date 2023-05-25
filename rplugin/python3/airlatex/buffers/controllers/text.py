from airlatex.lib.range import FenwickTree, NaiveAccumulator
from airlatex.lib.task import AsyncDecorator, Task

from difflib import SequenceMatcher
from hashlib import sha1

from copy import deepcopy

from logging import getLogger

class Text():

  def __init__(self):
    self.previous = []
    self.lines = NaiveAccumulator()

  @property
  def content_hash(self):
    # compute sha1-hash of current buffer
    tohash = ("blob " + str(self.lines[-1]) + "\x00") + "\n".join(self.previous[:])
    sha = sha1()
    sha.update(tohash.encode())
    return sha.hexdigest()

  def query(self, start, end):
    start_line, start_col = self.lines.search(start)
    end_line, end_col = self.lines.search(end)
    if start_line < 0:
      start_line = end_line
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
    if not self.previous:
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

  # inster string at given position
  def _insert(self, buffer, start, string):

    line, col = self.lines.search(start)
    # convert format to array-style
    addition = string.split("\n")

    # Directly mutating addition allows us to cover since line and multiline
    # case.
    addition[-1] += buffer[line][col:]
    start = buffer[line][:col] + addition[0]

    buffer[line] = start
    self.lines[line] = len(start) + 1

    # Still valid for multiline, since slices will return empties
    buffer[line + 1:line + 1] = addition[1:]
    for l in addition[1:][::-1]:
      self.lines.insert(line, len(l) + 1)
    if line == self.lines.last_index:
      self.lines[-1] -= 1

  # remove len chars from pos
  def _remove(self, buffer, start, string):

    line, col = self.lines.search(start)
    # convert format to array-style
    removal = string.split("\n")

    end_col = col + len(removal[-1])
    if len(removal) > 1:
      end_col -= col
    buffer[line] = buffer[line][:col] + buffer[line + len(removal) - 1][end_col:]
    self.lines[line] = len(buffer[line]) + 1

    for l in removal[1:]:
      del self.lines[line + 1]
      del buffer[line + 1]
    if line == self.lines.last_index:
      self.lines[-1] -= 1
