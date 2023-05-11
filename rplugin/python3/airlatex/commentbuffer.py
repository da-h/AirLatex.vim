import pynvim
from time import gmtime, strftime
from asyncio import Queue, Lock, sleep, create_task
from airlatex.documentbuffer import DocumentBuffer
from logging import getLogger, NOTSET
from airlatex.util import pynvimCatchException, generateCommentId
import time
import textwrap
import re


class CommentBuffer:

  def __init__(self, nvim, airlatex):
    self.nvim = nvim
    self.airlatex = airlatex
    self.buffer = None
    self.buffer_write_i = 0
    self.cursorPos = []
    self.log = getLogger("AirLatex")
    self.log.debug_gui("SideBar initialized.")
    self.cursor = (2, 0)

    self.project = None
    self.threads = {}
    self.index = 0

    self.symbol_open = self.nvim.eval("g:AirLatexArrowOpen")
    self.symbol_closed = self.nvim.eval("g:AirLatexArrowClosed")
    self.showArchived = self.nvim.eval("g:AirLatexShowArchived")
    self.status = "Initializing"
    self.creation = ""
    self.drafting = False

    self.uilock = Lock()

    self.comment_id = 1

  # ----------- #
  # AsyncIO API #
  # ----------- #

  async def triggerRefresh(self):
    self.log.debug("Refresh")
    self.log.debug_gui("trying to acquire (in trigger)")
    await self.uilock.acquire()
    self.nvim.async_call(self._render)

  async def updateStatus(self, msg):
    self.log.debug_gui("trying to acquire (in update)")
    self.status = msg
    self.log.debug_gui("updateStatus()")
    self.nvim.async_call(self.updateStatusLine)

  # ----------- #
  # GUI Drawing #
  # ----------- #

  @property
  def visible(self):
    buffer_id = self.buffer.number
    return self.nvim.call('bufwinnr', buffer_id) != -1

  @pynvimCatchException
  def updateStatusLine(self, releaseLock=True):
    if hasattr(self, 'statusline') and len(self.statusline):
      # self.nvim.command('setlocal ma')
      self.statusline[0] = self.statusline[0][:15] + self.status
      # self.nvim.command('setlocal noma')

  @pynvimCatchException
  def bufferappend(self, arg, pos=[]):
    if self.buffer_write_i >= len(self.buffer):
      self.buffer.append(arg)
    else:
      self.buffer[self.buffer_write_i] = arg
    self.buffer_write_i += 1
    if self.buffer_write_i == self.cursor[0]:
      self.cursorPos = pos

  def initGUI(self):
    self.log.debug_gui("initGUI()")
    self.initCommentBuffer()
    self.hide()

  @pynvimCatchException
  def initCommentBuffer(self):
    self.log.debug_gui("initCommentBuffer()")

    self.nvim.command(
        'let splitLocation = g:AirLatexWinPos ==# "left" ? "botright " : "topleft "'
    )
    self.nvim.command('let splitSize = g:AirLatexWinSize')

    self.nvim.command(
        """
            silent! exec splitLocation . 'vertical ' . splitSize . ' new'
            silent! exec "buffer " . "AirLatexComments"
        """)

    self.buffer = self.nvim.current.buffer

    self.nvim.command('file AirLatexComments')
    self.nvim.command('setlocal winfixwidth')

    # throwaway buffer options (thanks NERDTree)
    self.nvim.command('syntax clear')
    self.nvim.command('setlocal noswapfile')
    self.nvim.command('setlocal buftype=nofile')
    self.nvim.command('setlocal bufhidden=hide')
    self.nvim.command('setlocal wrap')
    self.nvim.command('setlocal foldcolumn=0')
    self.nvim.command('setlocal foldmethod=manual')
    self.nvim.command('setlocal nofoldenable')
    self.nvim.command('setlocal nobuflisted')
    self.nvim.command('setlocal nospell')
    self.nvim.command('setlocal nonu')
    self.nvim.command('setlocal nornu')
    self.nvim.command('iabc <buffer>')
    self.nvim.command('setlocal cursorline')
    self.nvim.command('setlocal filetype=airlatexcomment')

    # self.nvim.command("nnoremap <buffer> q<C-n> :call AirLatex_NextComment()<enter>")
    # self.nvim.command("cnoremap <buffer> w<CR> :call AirLatex_NextComment()<enter>")

    self.nvim.command(
        "nnoremap <buffer> <C-n> :call AirLatex_NextComment()<enter>")
    self.nvim.command(
        "nnoremap <buffer> <C-p> :call AirLatex_PrevComment()<enter>")

    self.nvim.command(
        "nnoremap <buffer> <enter> :call AirLatex_CommentEnter()<enter>")

    self.nvim.command("au InsertEnter <buffer> :call AirLatex_DraftResponse()")

    self.nvim.command(
        "nnoremap <buffer> ZZ :call AirLatex_FinishDraft(1)<enter>")
    self.nvim.command(
        "nnoremap <buffer> ZQ :call AirLatex_FinishDraft(0)<enter>")

    # Register Mappings
    # self.nvim.command("nnoremap <silent> <buffer> q :q <enter>")
    # self.nvim.command("nnoremap <silent> <buffer> <up> <up> <bar> :call AirLatex_SidebarRefresh() <enter> <bar> <right>")
    # self.nvim.command("nnoremap <silent> <buffer> k <up> <bar> :call AirLatex_SidebarRefresh() <enter> <bar> <right>")
    # self.nvim.command("nnoremap <silent> <buffer> <down> <down> <bar> :call AirLatex_SidebarRefresh() <enter> <bar> <right>")
    # self.nvim.command("nnoremap <silent> <buffer> j <down> <bar> :call AirLatex_SidebarRefresh() <enter> <bar> <right>")
    # self.nvim.command("nnoremap <silent> <buffer> <enter> :call AirLatex_ProjectEnter() <enter>")
    # self.nvim.command("autocmd VimLeavePre <buffer> :call AirLatex_Close()")
    # self.nvim.command("nnoremap <silent> <buffer> d :call AirLatex_ProjectLeave() <enter>")
    # self.nvim.command("nnoremap <silent> <buffer> D :call AirLatex_ProjectLeave() <enter>")

  @pynvimCatchException
  def render(self, project, threads):
    if self.uilock.locked():
      return

    self.project = project

    # Sort overlapping threads by time
    def lookup(thread):
      thread = project.comments.get(thread)
      if not thread:
        return -1
      for m in thread.get("messages", []):
        return m.get("timestamp", 0)
      return -1

    self.threads = sorted([t.data for t in threads], key=lookup)
    self.index = 0
    create_task(self.triggerRefresh())

  @pynvimCatchException
  def _render(self):
    self.log.debug(f"in render {self.threads, self.index}")
    self.buffer[:] = []

    if not self.threads:
      return
    # Reset
    self.drafting = False
    self.creation = ""

    thread = self.project.comments.get(self.threads[self.index])
    self.log.debug(f"id {self.threads[self.index]}")
    self.log.debug(f"thread {thread}")
    if not thread:
      self.log.debug(f"all {self.threads}")
      return
    self.log.debug_gui("Show thread")
    if self.buffer == self.nvim.current.window.buffer:
      self.cursor = self.nvim.current.window.cursor

    # self.nvim.command('setlocal ma')
    self.cursorPos = []

    size = self.nvim.eval("g:AirLatexWinSize")

    indicator = ""
    if len(self.threads) > 1:
      indicator = f" ({self.index + 1} / {len(self.threads)})"

    # Display Header
    self.buffer[0] = f"┄┄┄┄┄┄ Comments{indicator} ┄┄┄┄┄┄┄".center(size)
    if thread.get("resolved", False):
      self.bufferappend("!! Resolved")
    self.bufferappend("")

    for message in thread["messages"]:
      user = message['user']['first_name']
      content = message['content']
      timestamp = message['timestamp']

      # Convert timestamp to a short date format
      short_date = time.strftime(
          "%m/%d/%y %H:%M", time.gmtime(timestamp / 1000))

      space = size - len(user) - len(short_date) - 6
      user = f"  {user} │"
      self.bufferappend(f"¶{user} {' ' * space}{short_date}")
      self.bufferappend(
          "┌" + '─' * (len(user) - 1) + '┴' + '─' * (size - 2 - len(user)) +
          "┐")
      for line in textwrap.wrap(content, width=size - 3):
        self.bufferappend(f'│  {line}')
      self.bufferappend('└')
      self.bufferappend('')

    if thread.get("resolved", False):
      self.bufferappend(f" » reopen{' ' * (size - 4 - 7)}⬃⬃")
    else:
      self.bufferappend(f" » resolve{' ' * (size - 5 - 7)}✓✓")
    if self.uilock.locked():
      self.uilock.release()

  # ------- #
  # Actions #
  # ------- #

  def show(self, change=False):
    if not self.visible:
      # Create window (triggers au on document)
      # Move back (triggers au on document)
      # So set debounce prior ro creating window
      current_win_id = self.nvim.api.get_current_win()
      self.nvim.command('let splitSize = g:AirLatexWinSize')
      self.nvim.command(
          f"""
                exec 'vertical rightbelow sb{self.buffer.number}'
                exec 'buffer {self.buffer.number}'
                exec 'vertical rightbelow resize ' . splitSize
            """)
      if not change:
        self.nvim.api.set_current_win(current_win_id)

  def hide(self):
    if self.visible:
      current_buffer = self.nvim.current.buffer
      self.threads = {}
      self.index = 0
      self.creation = ""
      self.drafting = False
      self.buffer[:] = []
      if len(self.nvim.current.tabpage.windows) == 1:
        self.nvim.command("q!")
      elif current_buffer == self.buffer:
        self.nvim.command('hide')
      else:
        self.nvim.command('buffer AirLatexComments')
        self.nvim.command('hide')
        # Return to the original buffer
        self.nvim.command('buffer ' + current_buffer.name)

  @property
  def content(self):
    content = ""
    for line in self.buffer:
      if line.startswith("#"):
        continue
      content += line + "\n"
    return content

  @pynvimCatchException
  def finishDraft(self, submit):
    if self.drafting:
      self.drafting = False
      if not self.creation:
        if not submit:
          create_task(self.triggerRefresh())
          return
        self.project.replyComment(self.threads[self.index], self.content)
        create_task(self.triggerRefresh())
      else:
        doc = self.creation
        self.creation = ""
        if not submit:
          if self.previous_open:
            self.buffer[:] = []
            create_task(self.triggerRefresh())
          else:
            self.hide()
          return
        # TODO: Submit
        thread = generateCommentId(self.comment_id)
        self.comment_id += 1
        self.project.createComment(thread, doc, self.content)
        self.threads = [thread]
        self.index = 0
        create_task(self.triggerRefresh())

    # If on the other page
    else:
      self.hide()

  @pynvimCatchException
  def prepCommentCreation(self):
    self.previous_open = self.visible
    if self.visible:
      window = self.nvim.call('bufwinnr', self.buffer.number)
      self.nvim.command(f"exec '{window} wincmd w'")
    else:
      self.show(change=True)
    self.index = 0
    self.threads = {}
    self.nvim.feedkeys('i')

  @pynvimCatchException
  def prepCommentRespond(self):
    if not self.drafting:
      self.buffer[:] = []
      self.buffer[0] = ""
      self.buffer.append("")
      self.buffer.append("#")
      self.buffer.append("# Drafting comment.")
      self.buffer.append("# Lines starting with '#' will be ignored.")
      self.buffer.append("# Do ZZ to save and send.")
      self.buffer.append("# Do ZQ to quit without sending.")
      self.buffer.append("#")
      self.drafting = True

  @pynvimCatchException
  def changeComment(self, change):
    self.index = (self.index + change) % len(self.threads)
    create_task(self.triggerRefresh())

  @pynvimCatchException
  def toggle(self):
    if self.visible:
      self.hide()
    else:
      self.show()

  @pynvimCatchException
  def cursorAction(self, key="enter"):
    if key == "enter":
      resolve_pattern = re.compile(r'resolve\s+✓✓$')
      if resolve_pattern.search(self.nvim.current.line):
        self.project.resolveComment(self.threads[self.index])
        create_task(self.triggerRefresh())
      resolve_pattern = re.compile(r'reopen\s+⬃⬃$')
      if resolve_pattern.search(self.nvim.current.line):
        self.project.reopenComment(self.threads[self.index])
        create_task(self.triggerRefresh())
