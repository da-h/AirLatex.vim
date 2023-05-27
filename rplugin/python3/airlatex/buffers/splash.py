from time import gmtime, strftime

from airlatex.buffers.menu import PassiveMenuBuffer

from airlatex.lib.exceptions import pynvimCatchException
from airlatex.lib.uuid import generateCommentId
from airlatex.lib.task import Task, AsyncDecorator


class Splash(PassiveMenuBuffer):

  def __init__(self, nvim):
    super().__init__(nvim)
    self.log.debug("Splash Page Started")

  # ------- #
  #   Api   #
  # ------- #

  @pynvimCatchException
  def buildBuffer(self):

    buffer = self.nvim.current.buffer
    self.size = self.nvim.current.window.width - self.nvim.eval("g:AirLatexWinSize")

    self.command(
        """
        file AirLatexSplash
        setlocal winfixwidth
        syntax clear
        setlocal noswapfile
        setlocal buftype=nofile
        setlocal bufhidden=hide
        setlocal wrap
        setlocal foldcolumn=0
        setlocal foldmethod=manual
        setlocal nofoldenable
        setlocal nobuflisted
        setlocal nospell
        setlocal nonu
        setlocal nornu
        iabc <buffer>
        setlocal cursorline
        setlocal filetype=airlatexsplash
    """)
    return buffer

  @AsyncDecorator
  @pynvimCatchException
  def _render(self):
    # Display Header
    menu = self.menu.clear(title=f"Connection",
                           size=self.size)
    menu.add_blob("""
   _____  .__       .____            __
  /  _  \\ |__|______|    |   _____ _/  |_  ____ ___  ___
 /  /_\\  \\|  \\_  __ \\    |   \\__  \\\\   __\\/ __ \\\\  \\/  /
/    |    \\  ||  | \\/    |___ / __ \\|  | \\  ___/ >    <
\\____|__  /__||__|  |_______ (____  /__|  \\___  >__/\\_ \\
        \\/                  \\/    \\/          \\/      \\/

  The Following bindings are scoped to the buffers. If
  you'd like to customize them, please create a PR.

Buffer   | Binding      | Description
-------- | ------------ | ------------------------------
sidebar  | `q`          | Close buffer
sidebar  | `enter`      | Enter project/ Toggle folder
sidebar  | `d`, `D`     | Leave project
document | visual `gv`  | Mark for drafting a comment
document | `R`          | Refresh document/ bring online
document | command `:w` | Synced with github? Commits
comments | `<C-n>`      | Next comment (stacked cmnts)
comments | `<C-p>`      | Prev comment (stacked cmnts)
comments | `ZZ`         | Submit comment in draft
comments | `ZQ`         | Quit Buffer/ discard draft
comments | (insert)     | Draft response if on thread
comments | `enter`      | Un/resolve project on option.
""", indent = (self.size - 56)//2)

    self.write()
    if self.lock.locked():
      self.lock.release()
    self.log.debug(f"Finished Render")

  @pynvimCatchException
  def registerCursorActions(self, MenuItem, handle):
    pass
