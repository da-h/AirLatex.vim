from asyncio import Lock
from abc import ABC, abstractmethod

from airlatex.lib.task import Task

from logging import getLogger


class Buffer(ABC):

  def __init__(self, nvim, *args, **kwargs):
    self.nvim = nvim
    self.session = None
    self.buffer = None
    self.log = getLogger("AirLatex")
    self.lock = Lock()
    self.initialize(*args, **kwargs)

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

  def initialize(self, *args, **kwargs):
    self.buffer = self.buildBuffer(*args, **kwargs)

  @abstractmethod
  def buildBuffer(self, *args, **kwargs):
    pass
