from intervaltree import Interval, IntervalTree

from logging import getLogger

class Threads():

  def __init__(self):
    self.selection = IntervalTree()
    self.threads = IntervalTree()
    self.data = {}
    self.active = True

  def clear(self):
    self.threads.clear()

  # Should check
  def activate(self, text, cursor):
    cursor_offset = text.lines.position(cursor[0] - 1, cursor[1])
    threads = self.threads[cursor_offset]
    self.active = bool(threads)
    return threads

  def create(self, text, comments, thread):
    if not comments:
      return False, ()
    thread_id = thread.get("id")
    comments = comments.get(thread_id, {})
    resolved = comments.get("resolved", False)
    if resolved or not comments:
      return False, ()

    start = thread["op"]["p"]
    end = start + len(thread["op"]["c"])
    start_line, start_col, end_line, end_col = text.query(start, end)

    if start == end:
      start -= 1
      end += 1
      start_col = max(start_col - 1, 0)
      end_col = min(
          end_col + 1, text.lines[end_line] - text.lines[end_line - 1] - 1)
    self.threads[start:end] = thread_id
    return True, (start_line, start_col, end_line, end_col)

  # Mark comment
  def select(self, text, start_line, start_col, end_line, end_col):
    self.selection = IntervalTree()
    self.selection.add(
        Interval(
            text.lines.position(start_line, start_col),
            text.lines.position(end_line, end_col)))

  @property
  def doubled(self):
    overlapping_ranges = set()
    for interval in self.threads:
      overlaps = self.threads[interval.begin:interval.end]
      for overlap in overlaps:
        if overlap == interval:
          continue
        overlapping_range = Interval(
            max(interval.begin, overlap.begin), min(interval.end, overlap.end))
        # Redundant adds don't matter since set
        overlapping_ranges.add(overlapping_range)
    return overlapping_ranges


  def getNextPosition(self, offset):
    positions = self.threads[offset + 1:] - self.threads[offset]
    count = len(self.threads[:]) - len(positions) + 1
    if not positions:
      positions = self.threads[:offset] - self.threads[offset]
      count = 1
    if not positions:
      return (-1, -1), 0
    return min(positions).begin, count

  def getPrevPosition(self, offset):
    positions = self.threads[:offset] - self.threads[offset]
    count = len(positions)
    if not positions:
      positions = self.threads[offset + 1:] - self.threads[offset]
      count = 1
    if not positions:
      return (-1, -1), 0
    return max(positions).begin, count


  def applyOp(self, op, packet):

    # delete char and lines
    if 'd' in op:
      p = op['p']
      s = op['d']
      self._remove(p, p + len(s))

    # add characters and newlines
    if 'i' in op:
      p = op['p']
      s = op['i']
      self._insert(p, p + len(s))

    # add comment
    if 'c' in op:
      thread = {"id": op['t'], "metadata": packet["meta"], "op": op}
      self.data[op['t']] = thread

  def _remove(self, start, end):
    overlap = set({})
    delta = end - start
    for interval in self.threads[start:end + 1]:
      self.threads.remove(interval)
      begin = interval.begin + min(start - interval.begin, 0)
      # end = (interval.end -
      #        min(end, interval.end) +
      #        max(start, interval.begin) +
      #        min(start - interval.begin, 0))
      if end >= interval.end:
        stop = start
      else:
        stop = interval.end - delta
      if begin >= stop:
        stop = begin + 1
      interval = Interval(begin, stop, interval.data)
      overlap.add(interval)
    for interval in self.threads[end + 1:]:
      self.threads.remove(interval)
      self.threads.add(Interval(interval.begin - delta,
                                interval.end - delta,
                                interval.data))
    for o in overlap:
      self.threads.add(o)

  def _insert(self, start, end):
    overlap = set({})
    delta = end - start
    for interval in self.threads[start]:
        self.threads.remove(interval)
        end = interval.end + delta
        interval = Interval(interval.begin, end, interval.data)
        overlap.add(interval)
    for interval in self.threads[start + 1:]:
        self.threads.remove(interval)
        self.threads.add(Interval(interval.begin + delta, interval.end + delta, interval.data))

    for o in overlap:
      self.threads.add(o)
