import pynvim
from time import gmtime, strftime
from asyncio import Queue, Lock, sleep, create_task
from airlatex.documentbuffer import DocumentBuffer
from logging import getLogger, NOTSET
from airlatex.util import __version__, pynvimCatchException
import time
import textwrap


class CommentBuffer:
    def __init__(self, nvim, airlatex):
        self.nvim = nvim
        self.airlatex = airlatex
        self.buffer = None
        self.buffer_write_i = 0
        self.cursorPos = []
        self.log = getLogger("AirLatexComments")
        self.log.debug_gui("SideBar initialized.")
        self.cursor = (2, 0)

        self.project = None
        self.threads = []
        self.index = 0

        self.symbol_open=self.nvim.eval("g:AirLatexArrowOpen")
        self.symbol_closed=self.nvim.eval("g:AirLatexArrowClosed")
        self.showArchived = self.nvim.eval("g:AirLatexShowArchived")
        self.status = "Initializing"
        self.uilock = Lock()

    # ----------- #
    # AsyncIO API #
    # ----------- #

    async def triggerRefresh(self, all=True):
        self.log.debug_gui("trying to acquire (in trigger)")
        await self.uilock.acquire()
        self.log.debug_gui("triggerRefresh() -> event called")
        # self.nvim.async_call(self.listProjects, all)

    async def updateStatus(self, msg):
        self.log.debug_gui("trying to acquire (in update)")
        await self.uilock.acquire()
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
        if hasattr(self,'statusline') and len(self.statusline):
            # self.nvim.command('setlocal ma')
            self.statusline[0] = self.statusline[0][:15] + self.status
            # self.nvim.command('setlocal noma')
            if releaseLock and self.uilock.locked():
                self.uilock.release()

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
        create_task(self.uilock.acquire())

    @pynvimCatchException
    def initCommentBuffer(self):
        self.log.debug_gui("initCommentBuffer()")

        self.nvim.command('let splitLocation = g:AirLatexWinPos ==# "left" ? "botright " : "topleft "')
        self.nvim.command('let splitSize = g:AirLatexWinSize')

        self.nvim.command("""
            silent! exec splitLocation . 'vertical ' . splitSize . ' new'
            silent! exec "buffer " . "AirLatexComments"
        """)

        self.buffer = self.nvim.current.buffer

        self.nvim.command('file AirLatexComments')
        self.nvim.command('setlocal winfixwidth')

        # throwaway buffer options (thanks NERDTree)
        self.nvim.command('syntax clear')
        self.nvim.command('highlight User1 ctermfg=red guifg=red')
        self.nvim.command('highlight User2 ctermfg=blue guifg=blue')
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

        self.nvim.command("nnoremap <buffer> <C-n> :call AirLatex_NextComment()<enter>")
        self.nvim.command("nnoremap <buffer> <C-p> :call AirLatex_PrevComment()<enter>")

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
      self.project = project
      self.threads = [t.data for t in threads]
      self.index = 0
      return self._render()

    @pynvimCatchException
    def _render(self):
        self.log.debug(f"id {self.threads[self.index]}")
        thread = self.project.comments.get(self.threads[self.index])
        self.log.debug(f"thread {thread}")
        if not thread:
          self.log.debug(f"all {self.threads}")
          return
        self.log.debug_gui("Show thread")
        if self.buffer == self.nvim.current.window.buffer:
            self.cursor = self.nvim.current.window.cursor

        # self.nvim.command('setlocal ma')
        self.cursorPos = []

        self.buffer[:] = []
        # Display Header

        size = self.nvim.eval("g:AirLatexWinSize")

        indicator = ""
        if len(self.threads) > 1:
            indicator = f" ({self.index + 1} / {len(self.threads)})"

        self.bufferappend(f"┄┄┄┄┄┄ Comments{indicator} ┄┄┄┄┄┄┄".center(size))
        self.bufferappend("")

        for message in thread["messages"]:
            user = message['user']['first_name']
            content = message['content']
            timestamp = message['timestamp']

            # Convert timestamp to a short date format
            short_date = time.strftime("%m/%d/%y %H:%M", time.gmtime(timestamp / 1000))

            space = size - len(user) - len(short_date) - 6
            self.bufferappend(f"¶  {user} | {' ' * space}{short_date}")
            self.bufferappend("┌" + '─' * (size - 1))
            for line in textwrap.wrap(content, width=size - 3):
              self.bufferappend(f'│  {line}')
            self.bufferappend('└')
            self.bufferappend('')

            if user == 'chris':
                self.nvim.command(f"call matchadd('User1', '^¶  {user}')")
            else:
                self.nvim.command(f"call matchadd('User2', '^¶  {user}')")

        if self.uilock.locked():
            self.uilock.release()


    # ------- #
    # Actions #
    # ------- #

    def show(self):
        if not self.visible:
            current_buffer = self.nvim.current.buffer
            self.nvim.command('let splitSize = g:AirLatexWinSize')
            self.nvim.command(f"""
                exec 'vertical rightbelow sb{self.buffer.number}'
                exec 'buffer {self.buffer.number}'
                exec 'vertical rightbelow resize ' . splitSize
            """)
            create_task(self.triggerRefresh())

    def hide(self):
        if self.visible:
          current_buffer = self.nvim.current.buffer
          if current_buffer == self.buffer:
              self.nvim.command('hide')
          else:
              self.nvim.command('buffer AirLatexComments')
              self.nvim.command('hide')
              # Return to the original buffer
              self.nvim.command('buffer ' + current_buffer.name)

    @pynvimCatchException
    def changeComment(self, change):
        self.index = (self.index + change) % len(self.threads)
        self._render()

    @pynvimCatchException
    def toggle(self):
        if self.visible:
            self.hide()
        else:
            self.show()

    @pynvimCatchException
    def cursorAction(self, key="enter"):
      pass
