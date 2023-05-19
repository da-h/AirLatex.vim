import pynvim
from time import gmtime, strftime
from asyncio import Queue, Lock, sleep
from airlatex.documentbuffer import DocumentBuffer
from logging import getLogger, NOTSET
from airlatex.util import __version__, pynvimCatchException

from airlatex.task import AsyncDecorator, Task

class SideBar:

  def __init__(self, nvim, airlatex):
    self.nvim = nvim
    self.servername = self.nvim.eval("v:servername")
    self.airlatex = airlatex
    self.lastUpdate = gmtime()
    self.buffer = None
    self.buffer_write_i = 0
    self.cursorPos = []
    self.log = getLogger("AirLatex")
    self.cursor = (2, 0)

    self.symbol_open = self.nvim.eval("g:AirLatexArrowOpen")
    self.symbol_closed = self.nvim.eval("g:AirLatexArrowClosed")
    self.showArchived = self.nvim.eval("g:AirLatexShowArchived")
    self.status = "Initializing"
    self.uilock = Lock()

  # ----------- #
  # AsyncIO API #
  # ----------- #

  async def triggerRefresh(self, all=True):
    await self.uilock.acquire()
    return Task(self.listProjects, all)

  async def updateStatus(self, msg):
    await self.uilock.acquire()
    self.status = msg
    return Task(self.updateStatusLine)

  # ----------- #
  # GUI Drawing #
  # ----------- #

  @property
  def visible(self):
    buffer_id = self.buffer.number
    return self.nvim.call('bufwinnr', buffer_id) != -1

  def animation(parent, name):
    class Animation:
        def __enter__(self):
            self.task = Task(self._animate(name))
            return self.task

        def __exit__(self, exc_type, exc_value, exc_traceback):
            self.task.cancel()
            if exc_type is not None:
                parent.logger.debug(traceback.format_exc())
                Task(parent.updateStatus(f"{name} failed: {exc_value}"))
                return False
            return True  # This prevents the exception from being re-raised

        async def _animate(self, msg):
          i = 0
          while True:
            s = " .." if i % 3 == 0 else ". ." if i % 3 == 1 else ".. "
            await self.updateStatus(f"{s} {msg} {s}")
            await sleep(0.1)
            i += 1
    return Animation()

  @AsyncDecorator
  @pynvimCatchException
  def updateStatusLine(self, releaseLock=True):
    if hasattr(self, 'statusline') and len(self.statusline):
      self.statusline[0] = self.statusline[0][:15] + self.status
      if releaseLock and self.uilock.locked():
        self.uilock.release()

  @pynvimCatchException
  def bufferappend(self, arg, pos=[]):
    if self.buffer_write_i >= len(self.buffer):
      self.buffer.append(arg.rstrip())
    else:
      self.buffer[self.buffer_write_i] = arg.rstrip()
    self.buffer_write_i += 1
    if self.buffer_write_i == self.cursor[0]:
      self.cursorPos = pos

  def initGUI(self):
    self.initSidebarBuffer()
    Task(self.uilock.acquire())
    self._listProjects(False)

  def command(self, cmd):
    for c in cmd.split("\n"):
      self.log.debug(c)
      self.nvim.command(c.strip())

  @pynvimCatchException
  def initSidebarBuffer(self):

    self.command(
    """
      let splitSize = g:AirLatexWinSize
      let splitLocation = g:AirLatexWinPos ==# "left" ? "topleft " : "botright "
      exec splitLocation . 'vertical ' . splitSize . ' new'
      buffer "AirLatex"
    """)

    self.buffer = self.nvim.current.buffer

    # throwaway buffer options (thanks NERDTree)
    self.command("""
      file AirLatex
      setlocal winfixwidth
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
      setlocal filetype=airlatex
    """)
    # self.nvim.command('setlocal nomodifiable')

    # Register Mappings
    self.command("""
      nnoremap <silent> <buffer> q :q <enter>
      nnoremap <silent> <buffer> <up> <up> <bar> :call AirLatex_SidebarRefresh() <enter> <bar> <right>
      nnoremap <silent> <buffer> k <up> <bar> :call AirLatex_SidebarRefresh() <enter> <bar> <right>
      nnoremap <silent> <buffer> <down> <down> <bar> :call AirLatex_SidebarRefresh() <enter> <bar> <right>
      nnoremap <silent> <buffer> j <down> <bar> :call AirLatex_SidebarRefresh() <enter> <bar> <right>
      nnoremap <silent> <buffer> <enter> :call AirLatex_ProjectEnter() <enter>
      nnoremap <silent> <buffer> d :call AirLatex_ProjectLeave() <enter>
      nnoremap <silent> <buffer> D :call AirLatex_ProjectLeave() <enter>
      autocmd VimLeavePre <buffer> :call AirLatex_Close()
    """)

  @AsyncDecorator
  @pynvimCatchException
  def listProjects(self, overwrite=False):
    self._listProjects(overwrite)

  def _listProjects(self, overwrite=False):
    if self.buffer == self.nvim.current.window.buffer:
      self.cursor = self.nvim.current.window.cursor

    # self.nvim.command('setlocal ma')
    self.cursorPos = []
    if self.airlatex.session:
      projectList = self.airlatex.session.projectList
    else:
      projectList = []
      self.status = "Starting Session"

    # Display Header
    self.buffer_write_i = 0
    self.bufferappend("   ┄┄┄┄┄┄ AirLatex (ver %s) ┄┄┄┄┄┄┄" % __version__)
    self.bufferappend(" ")

    # Display all Projects
    if projectList is not None:
      for i, project in enumerate(projectList):
        pos = [project]

        # skip deleted projects
        if project.get("trashed"):
          continue

        # skip archived projects
        if project.get("archived") and not self.showArchived:
          continue

        # list project structure
        if project.get("open"):
          self.bufferappend(" " + self.symbol_open + " " + project["name"], pos)
          self.log.debug(f"{project}")
          self.listProjectStructure(project.get("rootFolder", [None])[0], pos)
        else:
          self.bufferappend(
              " " + self.symbol_closed + " " + project["name"], pos)

        # cursor-over info
        if self.cursorAt([project]):
          if project.get("open"):
            self.bufferappend("   -----------------")
        if "msg" in project and (project.get("connected") or
            (self.cursorAt([project]) and project.get("msg",
                                                      "").startswith("Error"))):
          if project["msg"].startswith("Error: "):
            self.bufferappend("   error: " + project['msg'][7:])
          else:
            self.bufferappend("   msg: " + project['msg'])
        if self.cursorAt([project]):
          if "await" not in project:
            self.bufferappend("   awaits: [enter to connect]")
          else:
            self.bufferappend(
                "   awaits: " + ("↑" if not project["await"] else "↓"))
          if "source" in project:
            self.bufferappend("   source: " + project['source'])
          if "owner" in project:
            self.bufferappend(
                "   owner: " + project['owner'].get('firstName', '') + (
                    " " + project['owner'].get('lastName') if "lastName" in
                    project["owner"] else ""))
          if "lastUpdated" in project:
            self.bufferappend("   last change: " + project['lastUpdated'])
          if not (project.get("lastUpdatedBy") == None):
            self.bufferappend(
                "    -> by: " + project['lastUpdatedBy']['firstName'] + " " +
                " " + project['lastUpdatedBy'].get('lastName', ''))

    # Info
    self.bufferappend("  ")
    self.bufferappend("  ")
    self.bufferappend("  ")
    self.bufferappend(" Retry       : enter", ["retry"])
    self.bufferappend(" Status      : %s" % self.status, ["status"])
    self.statusline = self.buffer.range(
        self.buffer_write_i, self.buffer_write_i + 1)
    self.updateStatusLine(releaseLock=False)
    self.bufferappend(
        " Last Update : " + strftime("%H:%M:%S", self.lastUpdate),
        ["lastupdate"])
    self.bufferappend(" Quit All    : enter", ["disconnect"])
    # if not overwrite:
    #   self.vimCursorSet(3, 1)
    del (self.buffer[self.buffer_write_i:len(self.buffer)])
    # self.nvim.command('setlocal noma')

    if self.uilock.locked():
      self.uilock.release()

  @pynvimCatchException
  def listProjectStructure(self, rootFolder, pos, indent=0):
    if not rootFolder:
      self.bufferappend("Unable to load folders")
      return

    # list folders first
    indentStr = "   " + "  " * indent
    for folder in rootFolder["folders"]:
      folder["type"] = "folder"
      if "open" in folder and folder["open"]:
        self.bufferappend(
            indentStr + self.symbol_open + " " + folder["name"], pos + [folder])
        self.listProjectStructure(folder, pos + [folder], indent + 1)
      else:
        self.bufferappend(
            indentStr + self.symbol_closed + " " + folder["name"],
            pos + [folder])

    # list editable files
    indentStr = "   " + "  " * (indent + 1)
    for doc in rootFolder["docs"]:
      doc["type"] = "file"
      self.bufferappend(indentStr + doc["name"], pos + [doc])

    # list files (other files)
    if len(rootFolder["fileRefs"]) > 0:
      self.bufferappend("   file Refs:", pos + ["fileRefs"])
      for file in rootFolder["fileRefs"]:
        file["type"] = "fileRef"
        self.bufferappend("    - " + file["name"], pos + [file])

  # ------- #
  # Actions #
  # ------- #

  def show(self):
    if not self.visible:
      self.nvim.command(
          'let splitType = g:AirLatexWinPos ==# "left" ? "vertical " : ""')
      self.nvim.command('let splitSize = g:AirLatexWinSize')
      self.nvim.command(
          f"""
                exec splitType . 'sb{self.buffer.number}'
                exec 'buffer {self.buffer.number}'
                exec splitType . 'resize ' . splitSize
            """)
      Task(self.triggerRefresh())

  def hide(self):
    if self.visible:
      current_buffer = self.nvim.current.buffer
      sidebar_buffer = self.airlatex.sidebar.buffer
      if current_buffer == sidebar_buffer:
        self.nvim.command('hide')
      else:
        self.nvim.command('buffer AirLatex')
        self.nvim.command('hide')
        # Return to the original buffer
        self.nvim.command('buffer ' + current_buffer.name)

  @pynvimCatchException
  def compile(self):
    if self.visible:
      self.hide()
    else:
      self.show()

  @pynvimCatchException
  def toggle(self):
    if self.visible:
      self.hide()
    else:
      self.show()

  @pynvimCatchException
  def _toggle(self, dict, key, default=True):
    if key not in dict:
      dict[key] = default
    else:
      dict[key] = not dict[key]

  @pynvimCatchException
  def vimCursorSet(self, row, col):
    if self.buffer == self.nvim.current.window.buffer:
      window = self.nvim.current.window
      window.cursor = (row, col)

  @pynvimCatchException
  def cursorAt(self, pos):

    # no pos given
    if not isinstance(pos, list):
      return False

    # cannot be at same position (pos is specified in more detail)
    if len(pos) > len(self.cursorPos):
      return False

    # check if all positions match
    for p, c in zip(pos, self.cursorPos):
      if p != c:
        return False
    return True

  @pynvimCatchException
  def cursorAction(self, key="enter"):
    self.log.debug(
        "cursorAction(%s) on %s")

    if not isinstance(self.cursorPos, list):
      return
    self.log.debug(
        "cursorAction(%s) on %s" %
        (key, ",".join(str(p) for p in self.cursorPos)))

    if len(self.cursorPos) == 0:
      pass

    elif len(self.cursorPos) == 1:

      # disconnect all
      if self.cursorPos[0] == "disconnect":
        if self.airlatex.session:
          self.airlatex.session.cleanup()

      # disconnect all
      elif self.cursorPos[0] == "retry":
        if self.airlatex.session:
          Task(self.airlatex.session.login())

      # else is project
      elif not isinstance(self.cursorPos[0], str):
        project = self.cursorPos[0]
        if "handler" in project:
          if key == "enter":
            self._toggle(self.cursorPos[-1], "open", default=False)
          elif key == "del":
            # So careful, because project is a shared object. It needs to be
            # shared such that it is stateful in the sidebar. Connected has
            # different implications for being True, False and None. We set it
            # back to None here such that it can properly be set later.
            if project.get("connected"):
              @Task(project["handler"].disconnect).fn()
              async def del_connect(*args):
                if "connected" in project:
                  del project["connected"]
          Task(self.triggerRefresh())
        else:
          self.log.debug(f"connecting {project}")
          Task(self.airlatex.session.connectProject(project))

    elif not isinstance(self.cursorPos[-1], dict):
      pass

    # is folder
    elif self.cursorPos[-1]["type"] == "folder":
      self._toggle(self.cursorPos[-1], "open")
      Task(self.triggerRefresh())

    # is file
    elif self.cursorPos[-1]["type"] == "file":
      name = DocumentBuffer.getName(self.cursorPos)
      for buffer, document in DocumentBuffer.allBuffers.items():
        self.log.debug(f"{name} vs {document.name}")
        if name == document.name:
          self.nvim.command('wincmd w')
          self.nvim.command(f'buffer {buffer.number}')
          return
      documentbuffer = DocumentBuffer(self.cursorPos, self.nvim)
      self.log.debug(f"{self.cursorPos}")
      Task(self.cursorPos[0]["handler"].joinDocument(documentbuffer))
