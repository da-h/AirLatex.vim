import traceback
from logging import NOTSET


def pynvimCatchException(fn, fallback=None):

  def wrapped(self, *args, **kwargs):
    try:
      return fn(self, *args, **kwargs)
    except Exception as e:
      self.log.debug(
          f"Error:. This is an unexpected Exception, "
          "thus stopping AirLatex. Please check the logfile "
          "& consider writing an issue to help improving the code.")
      self.log.debug(traceback.format_exc())
      if self.log.level == NOTSET:
        self.nvim.err_write(traceback.format_exc(e) + "\n")

      if fallback is not None:
        return fallback

  return wrapped
