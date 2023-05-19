from time import gmtime, strftime

from airlatex.task import AsyncDecorator, Task
from airlatex.buffers.buffers import ActiveMenuBuffer
from airlatex.lib import pynvimCatchException
from airlatex import __version__


class Sidebar(ActiveMenuBuffer):

  def __init__(self, nvim):
    super().__init__(nvim)

    self.symbol_open = self.nvim.eval("g:AirLatexArrowOpen")
    self.symbol_closed = self.nvim.eval("g:AirLatexArrowClosed")
    self.showArchived = self.nvim.eval("g:AirLatexShowArchived")
    self.status = "Initializing"

  @pynvimCatchException
  def buildBuffer(self):
    # Make the window
    self.command(
    """
      let splitSize = g:AirLatexWinSize
      let splitLocation = g:AirLatexWinPos ==# "left" ? "topleft " : "botright "
      exec splitLocation . 'vertical ' . splitSize . ' new'
      buffer "AirLatex"
    """)
    buffer = self.nvim.current.buffer

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
    return buffer

  @AsyncDecorator
  def _render(self):
    if self.buffer == self.nvim.current.window.buffer:
      self.cursor = self.nvim.current.window.cursor

    if self.session:
      projectList = self.session.projectList
    else:
      projectList = []
      self.status = "Starting Session"

    menu = Menu(title="",)

    # Display all Projects
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
        menu.add_entry(" {self.symbol_open} {project['name']}", project)
        for folder in project.get("rootFolder", [None]):
          self._listProjectStructure(folder, pos)
      else:
        menu.add_entry(" {self.symbol_closed} {project['name']}", project)

      menu = Menu(title="Title")
      menu.add_entry(" {self.symbol_closed} {project['name']}",
                     MenuItem.Actions.Disconnect())
      menu.from_dicitionary(
          keys=[("open", "-----------------"),
                ("msg", "Status: {}"),
                ("await", "Await: {}"),
                ("source", "Source: {}"),
                ("owner", "Owner {firstname}, {lastname}"), # Owner is a dictionary
                ("lastUpdated", "{}"),
                (("firstName", "lastName"), "User: {} {}")],
          data=project)

    # Info
    menu.space(3)
    menu.add_bulk((" Retry       : enter", ["retry"]),
    (" Status      : %s" % self.status, ["status"]),
    (" Last Update : " + strftime("%H:%M:%S", gmtime()), ["lastupdate"]),
    menu.add_entry(" Quit All    : enter", ["disconnect"]))

    if self.lock.locked():
      self.lock.release()

  @pynvimCatchException
  def _listProjectStructure(self, root, pos, menu, indent=0):
    if not root:
      menu.add_entry("Unable to load folders")
      return

    for folder in root["folders"]:
      folder["type"] = "folder"
      if "open" in folder and folder["open"]:
        menu.add_entry(f"{self.symbol_open} {folder['name']}", indent=indent)
        self._listProjectStructure(folder, pos + [folder], menu, indent = indent + 1)
      else:
        menu.add_entry(f"{self.symbol_closed} {folder['name']}", indent=indent)

    for doc in root["docs"]:
      doc["type"] = "file"
      menu.add_entry(doc['name'], indent=indent + 1)

    # list files (other files)
    if len(rootFolder["fileRefs"]) > 0:
      menu.add_entry("file Refs:", indent=indent + 1)
      for file in rootFolder["fileRefs"]:
        file["type"] = "fileRef"
        menu.add_entry(f" - {file['name']}", indent=indent + 1)

  @pynvimCatchException
  def registerCursorActions(self, handle):

    @handle(MenuItem.Actions.Disconnect)
    def disconnect():
      if self.airlatex.session:
        self.airlatex.session.cleanup()

    @handle(Actions.Retry)
    def retry():
      if self.airlatex.session:
        Task(self.airlatex.session.login())

    @handle(Project)
    def open(project):
      if "handler" in project:
        self._toggle(self.cursorPos[-1], "open", default=False)
      else:
        self.log.debug(f"connecting {project}")
        Task(self.airlatex.session.connectProject(project))

    @handle(Project, "del")
    def close(project):
      if "handler" in project:
        # So careful, because project is a shared object. It needs to be
        # shared such that it is stateful in the sidebar. Connected has
        # different implications for being True, False and None. We set it
        # back to None here such that it can properly be set later.
        if project.get("connected"):
          @Task(project["handler"].disconnect).fn()
          async def del_connect(*args):
            if "connected" in project:
              del project["connected"]

    @handle(Folder)
    def toggle(folder):
      self._toggle(self.cursorPos[-1], "open")
      Task(self.triggerRefresh())

    @handle(File)
    def join(document):
      name = DocumentBuffer.getName(document.file)
      for buffer, document in DocumentBuffer.allBuffers.items():
        self.log.debug(f"{name} vs {document.name}")
        if name == document.name:
          self.command('wincmd w')
          self.command(f'buffer {buffer.number}')
          return
      Task(document.party.joinDocument(document.file))

  def animation(self, name):
    return Animation(self.updateStatus, name)

  async def updateStatus(self, msg):
    await self.lock.acquire()
    self.status = msg
    return Task(self.updateStatusLine)
