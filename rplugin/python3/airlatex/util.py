import time
import logging


__version__ = "0.2"


# Generate a timstamp with a length of 13 numbers
def _genTimeStamp():
    t = time.time()
    t = str(t)
    t = t[:10]+t[11:]
    while len(t) < 13:
        t += "0"
    return t

# get logging
logging_settings={
    "level": "NOTSET",
    "file": "AirLatex.log",
    "gui": True
}

def init_logger():
    log = logging.getLogger("AirLatex")

    # user settings
    level=logging_settings["level"]
    file=logging_settings["file"]

    # gui related logging
    DEBUG_LEVEL_GUI = 9
    logging.addLevelName(DEBUG_LEVEL_GUI, "DEBUG_GUI")
    def debug_gui(self, message, *args, **kws):
        if self.isEnabledFor(DEBUG_LEVEL_GUI) and logging_settings["gui"]:
            self._log(DEBUG_LEVEL_GUI, message, args, **kws)
    logging.Logger.debug_gui = debug_gui
    logging.DEBUG_GUI = DEBUG_LEVEL_GUI

    if level != "NOTSET":

        # formatter
        f = logging.Formatter('%(name)s #%(lineno)d: %(message)s')

        # handler
        h = logging.FileHandler(file, "w")
        h.setFormatter(f)

        # logger settings
        log.addHandler(h)
        log.setLevel(getattr(logging,level))

    return log


