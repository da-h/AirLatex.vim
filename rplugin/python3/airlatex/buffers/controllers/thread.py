def get_threads(cursor)
  cursor_offset = self.cumulative_lines.position(cursor[0] - 1, cursor[1])
  threads = self.thread_intervals[cursor_offset]

def maybe_highlight
  def highlightComment(self, comments, thread):
    thread_id = thread["id"]
    if not comments:
      return
    comments = comments.get(thread_id, {})
    resolved = comments.get("resolved", False)
    if resolved or not comments:
      return

    start = thread["op"]["p"]
    end = start + len(thread["op"]["c"])

    char_count, start_line, start_col, end_line, end_col = self.getLineInfo(
        start, end)
    # Apply the highlight
    self.log.debug(
        f"highlight {start_line} {start_col} {end_line} {end_col} |"
        f"{start, end}")

    if start == end:
      start -= 1
      end += 1
      start_col = max(start_col - 1, 0)
      end_col = min(
          end_col + 1, char_count + self.cumulative_lines[end_line] - 1)
    self.thread_intervals[start:end] = thread_id

# Mark comment
def apply_selection
    if self.comment_selection.is_empty():
      self.comment_selection = IntervalTree()
      start_line, start_col, end_line, end_col = lineinfo
      self.comment_selection.add(
          Interval(
              self.cumulative_lines.position(start_line, start_col),
              self.cumulative_lines.position(end_line, end_col)))

def double_hihglights
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


  cursor
  cursor_offset
  def getCommentPosition(self, next: bool = False, prev: bool = False):
    if next == prev:
      return (-1, -1), 0

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
