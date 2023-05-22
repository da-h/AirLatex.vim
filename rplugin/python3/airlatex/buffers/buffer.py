from asyncio import Lock
from abc import ABC, abstractmethod

from airlatex.lib.task import Task

from logging import getLogger


class Buffer(ABC):

  def __init__(self, nvim):
    self.nvim = nvim
    self.session = None
    self.buffer = None
    self.log = getLogger("AirLatex")
    self.lock = Lock()
    self.initialize()

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
    return Task(self.lock.acquire).then(self._render)

  @abstractmethod
  def buildBuffer(self, *args, **kwargs):
    pass
