import time
import traceback
import logging
import platform
from sys import version_info
from logging import NOTSET

# get logging
class CustomLogRecord(logging.LogRecord):

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.filename = self.filename.split(".")[0]
    self.origin = f"{time.time()} | {self.filename} / {self.funcName} #{self.lineno:<4}"


def init_logger(level, file):
  log = logging.getLogger("AirLatex")
  if level != "NOTSET":

    # formatter
    logging.setLogRecordFactory(CustomLogRecord)
    f = logging.Formatter('%(origin)40s: %(message)s')

    # handler
    h = logging.FileHandler(file, "w")
    h.setFormatter(f)

    # logger settings
    log.addHandler(h)
    log.setLevel(getattr(logging, level))

  log.info(
      f"""Starting AirLatex (Version {__version__})
  System Info:
        - Python Version: {version_info.major}.{version_info.minor}
        - OS: {platform.system()} ({platform.release()})""")
  return log

