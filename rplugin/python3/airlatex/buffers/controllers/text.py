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
    if start_line < 0:
      start_line = end_line
    return char_count, start_line, start_col, end_line, end_col


  @property
  def content_hash(self):
    # compute sha1-hash of current buffer
    cumulative_lines = self.cumulative_lines
    # compute sha1-hash of current buffer
    buffer_cpy = self.saved_buffer[:]
    current_len = 0
    for i, row in enumerate(buffer_cpy):
      current_len += len(row) + 1
    current_len -= 1
    tohash = ("blob " + str(current_len) + "\x00")
    self.log.debug(f"Lengths {current_len, self.cumulative_lines[-1]}")
    self.log.debug(f"Lengths {current_len, self.cumulative_lines2[-1]}")

    tohash = ("blob " + str(current_len) + "\x00") + "\n".join(buffer_cpy)
    sha = sha1()
    sha.update(tohash.encode())
    return sha.hexdigest()

  def writeLines(buffer, lines):
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
    self.cumulative_lines.initialize(lengths)
    self.saved_buffer = buffer[:]

  def writeBuffer(self, comments=None):
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
        self.log.debug(f"Insert")
        selection = buffer[op[3]:op[4]]
        s = "\n".join(selection)
        for l in selection[::-1]:
          if op[3] == self.cumulative_lines.last_index:
            if op[3]:
              self.cumulative_lines[op[3] - 1] += 1
            self.cumulative_lines.insert(op[3], len(l))
          else:
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
          # If last line previous line needs to remove new line char
          if op[3] and op[3] == self.cumulative_lines.last_index:
            self.cumulative_lines[op[3] - 1] -= 1
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
        selection = buffer[op[3]:op[4]]
        new = "\n".join(selection)
        # Since Sequence Matcher works in order, we need to use the indices on
        # the buffer.
        for i, s in zip(range(op[3], op[4]), selection):
          # Account for new lines at end of document
          if i == self.cumulative_lines.last_index:
            self.cumulative_lines[i] = len(s)
          else:
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


  def applyOps(self, ops):
    @Task(self.lock.acquire).fn(self, ops, vim=True)
    def applyOps(self, ops):
      try:
        for op in ops:
          self.log.debug(f"the op {op} and {'c' in op}")

          # delete char and lines
          if 'd' in op:
            p = op['p']
            s = op['d']
            self._remove(self.buffer, p, s)

          # add characters and newlines
          if 'i' in op:
            p = op['p']
            s = op['i']
            self._insert(self.buffer, p, s)

          # add comment
          if 'c' in op:
            thread = {"id": op['t'], "metadata": packet["meta"], "op": op}
            self.threads[op['t']] = thread
            Task(self.highlightComments(comments))
        self.saved_buffer = self.buffer[:]
      except Exception as e:
        self.log.debug(f"{op} failed: {e}")
      finally:
        self.lock.release()

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
