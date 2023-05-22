from abc import ABC, abstractmethod

from airlatex.buffers.buffer import Buffer
from airlatex.buffers.controllers.menu import Menu

from airlatex.lib.task import Task
from airlatex.lib.exceptions import pynvimCatchException



class MenuBuffer(Buffer):

  def __init__(self, nvim, actions=None):
    super().__init__(nvim)
    self.menu = Menu()
    if actions is not None:
      self.menu = Menu(actions=actions)

  async def triggerRefresh(self, *args, **kwargs):
    await self.lock.acquire()
    return Task(self._render, *args, **kwargs)

  def clear(self):
    self.log.debug("clear")

    @Task(self.lock.acquire()).fn(vim=True)
    def callback():
      self.buffer[:] = []
      self.lock.release()

  def render(self, *args, **kwargs):
    Task(self.triggerRefresh)

  @abstractmethod
  def _render(self):
    pass

  def hide(self):
    if self.visible:
      current_buffer = self.nvim.current.buffer
      self.hideHook()
      if len(self.nvim.current.tabpage.windows) == 1:
        self.nvim.command("q!")
      if current_buffer == self.buffer:
        self.command('hide')
      else:
        self.command(f'buffer {self.buffer.name}')
        self.command('hide')
        # Return to the original buffer
        self.command(f'buffer {current_buffer.name}')

  def hideHook(self):
    pass

  @abstractmethod
  def show(self, *args, **kwargs):
    pass

  @abstractmethod
  def registerCursorActions(self, handle):
    pass

  @pynvimCatchException
  def toggle(self):
    if self.visible:
      self.hide()
    else:
      self.show()


class ActiveMenuBuffer(MenuBuffer):

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)

  def show(self):
    if not self.visible:
      self.command(
          f"""
          let splitSize = g:AirLatexWinSize
          let splitType = g:AirLatexWinPos ==# "left" ? "vertical " : ""
          exec splitType . 'sb{self.buffer.number}'
          exec 'buffer {self.buffer.number}'
          exec splitType . 'resize ' . splitSize
      """)
      Task(self.triggerRefresh())


class PassiveMenuBuffer(MenuBuffer):

  def __init__(self, *args, position="vertical rightbelow", **kwargs):
    super().__init__(*args, **kwargs)
    self._position = position

  def show(self, change=False):
    if not self.visible:
      # Create window (triggers au on document)
      # Move back (triggers au on document)
      # So set debounce prior to creating window
      current_win_id = self.nvim.api.get_current_win()
      self.nvim.command(
          f"""
        {self._position} sb{self.buffer.number}
        buffer {self.buffer.number}
        exec '{self._position} resize ' . g:AirLatexWinSize
      """)
      if not change:
        self.nvim.api.set_current_win(current_win_id)
      Task(self.triggerRefresh())
