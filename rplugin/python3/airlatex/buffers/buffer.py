from asyncio import Lock, sleep
from abc import ABC, abstractmethod

from airlatex.task import AsyncDecorator, Task

from logging import getLogger

class Buffer(ABC):

  def __init__(self, nvim):
    self.nvim = nvim
    self.session = None
    self.buffer = None
    self.log = getLogger("AirLatex")
    self.lock = Lock()

  @property
  def visible(self):
    if not self.buffer:
      return False
    buffer_id = self.buffer.number
    return self.nvim.call('bufwinnr', buffer_id) != -1

  def command(self, cmd):
    for c in cmd.split("\n"):
      self.log.debug(c)
      self.nvim.command(c.strip())

  def initialize(self):
    self.buffer = self.buildBuffer()
    return Task(self.lock.acquire).then(self.render)

  @abstractmethod
  def buildBuffer(self, *args, **kwargs):
    pass

class Animation():
  def __init__(self, name, callback):
    self.name = name
    self.callback = callback

  def __enter__(self):
    self.task = Task(self._animate(self.name))
    return self.task

  def __exit__(self, exc_type, exc_value, exc_traceback):
    self.task.cancel()
    if exc_type is not None:
      getLogger("AirLatex").debug(traceback.format_exc())
      Task(self.callback.updateStatus(f"{self.name} failed: {exc_value}"))
      return False
    return True  # This prevents the exception from being re-raised

  async def _animate(self, msg):
    i = 0
    while True:
      s = " .." if i % 3 == 0 else ". ." if i % 3 == 1 else ".. "
      await self.callback(f"{s} {msg} {s}")
      await sleep(0.1)
      i += 1
