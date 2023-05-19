def pynvimCatchException(fn, alt=None):

  def wrapped(self, *args, **kwargs):
    try:
      return fn(self, *args, **kwargs)
    except Exception as e:
      self.log.debug(
          f"Error: {e}. This is an unexpected Exception, "
          "thus stopping AirLatex. Please check the logfile "
          "& consider writing an issue to help improving the code.")
      self.log.debug(traceback.format_exc())
      if self.log.level == NOTSET:
        self.nvim.err_write(traceback.format_exc(e) + "\n")
      else:
        self.log.exception(
            "Uncaught exception occured. Please consider the log file.")
        self.log.exception(str(e))

      if alt is not None:
        return alt

  return wrapped
