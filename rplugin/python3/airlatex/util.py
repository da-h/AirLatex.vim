import time

# Generate a timstamp with a length of 13 numbers
def _genTimeStamp():
    t = time.time()
    t = str(t)
    t = t[:10]+t[11:]
    while len(t) < 13:
        t += "0"
    return t

# get logging
import logging
logging_settings={
    "level": "NOTSET",
    "file": "AirLatex.log",
    "gui": False
}

def getLogger(name):
    log = logging.getLogger(name)

    # user settings
    level=logging_settings["level"]
    file=logging_settings["file"]

    if level != "NOTSET":

        # formatter
        f = logging.Formatter('[%(levelname)s] %(name)s #%(lineno)d: (%(threadName)-10s) %(message)s')

        # handler
        h = logging.FileHandler(file)
        h.setFormatter(f)

        # logger settings
        log.addHandler(h)
        log.setLevel(getattr(logging,level))

    # gui related logging
    DEBUG_LEVEL_GUI = 9
    logging.addLevelName(DEBUG_LEVEL_GUI, "DEBUG_GUI")
    def debug_gui(self, message, *args, **kws):
        if self.isEnabledFor(DEBUG_LEVEL_GUI) and logging_settings["gui"]:
            self._log(DEBUG_LEVEL_GUI, message, args, **kws)
    logging.Logger.debug_gui = debug_gui

    return log


