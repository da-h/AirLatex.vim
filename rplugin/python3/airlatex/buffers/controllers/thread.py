from intervaltree import Interval, IntervalTree

class Threads():

  def __init__(self):
    self.selection = IntervalTree()
    self.threads = IntervalTree()
    self.data = {}

  def clear(self):
    self.threads.clear()

  # Should check
  def get(self, text, cursor):
    cursor_offset = text.lines.position(cursor[0] - 1, cursor[1])
    return self.threads[cursor_offset]

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
            max(interval.begin, overlap.begin),
            min(interval.end, overlap.end))
        # Redundant adds don't matter since set
        overlapping_ranges.add(overlapping_range)
    return overlapping_ranges


  def getPrevPosition(self, offset):
    positions = self.threads[
        offset + 1:] - self.threads[offset]
    offset = len(self.threads[:]) - len(positions) + 1
    if not positions:
      positions = self.threads[:offset] - self.threads[offset]
      offset = 1
    if not positions:
      return (-1, -1), 0
    return min(positions).begin, offset

  def getNextPosition(self, offset):
    positions = self.threads[:offset] - self.threads[
        offset]
    offset = len(positions)
    if not positions:
      positions = self.threads[offset + 1:] - self.threads[offset]
      offset = 1
    if not positions:
      return (-1, -1), 0
    return max(positions).begin, offset
