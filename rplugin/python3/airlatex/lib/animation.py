from abc import ABC, abstractmethod
from logging import getLogger
import traceback

from tornado.ioloop import PeriodicCallback


class Animation(ABC):

  def __init__(self, name, callback, loop=0.1):
    self.name = name
    self.callback = callback
    self.loop = PeriodicCallback(self._animate, 10000 * loop)  # default of 0.1 seconds
    self.i = 0

  def __enter__(self):
    self.loop.start()
    return self

  def __exit__(self, exc_type, exc_value, exc_traceback):
    self.loop.stop()
    if exc_type is not None:
      getLogger("AirLatex").debug(traceback.format_exc())
      Task(self.callback.updateStatus(f"{self.name} failed: {exc_value}"))
      return False
    return True  # This prevents the exception from being re-raised

  async def _animate(self):
    animated_string = self.animate(self.i, self.name)
    self.i += 1
    await self.callback(animated_string)

  def animate(self, i, msg):
    """return animated string"""


class Basic(Animation):

  def animate(self, i, msg):
    spacing = " .." if i % 3 == 0 else ". ." if i % 3 == 1 else ".. "
    return f"{spacing} {msg} {spacing}"
