from time import gmtime, strftime

from airlatex.lib.task import AsyncDecorator, Task
from airlatex.lib.exceptions import pynvimCatchException

from airlatex.buffers.document import Document

from airlatex.buffers.menu import ActiveMenuBuffer
from airlatex.lib.animation import Basic as Animation
from airlatex.lib.exceptions import pynvimCatchException
from airlatex.lib.settings import __version__


class Sidebar(ActiveMenuBuffer):

  def __init__(self, nvim, session):
    super().__init__(
        nvim,
        actions={
            'File': ['project', 'path', 'file'],
            'Folder': ['data'],
            'Project': ['data'],
            'Actions': {
                'Retry': [],
                'Disconnect': []
            }
        })

    self.session = session

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
    self.command(
        """
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

    # Register Mappings
    # search('▸', 'bW')<CR>
    jump = "<bar> :call AirLatex_SidebarRefresh() <enter> <bar> ^f▸"
    self.command(
        f"""
      nnoremap <silent> <buffer> q :q <enter>
      au CursorMoved <buffer> call AirLatex_SidebarRefresh()
      nnoremap <silent> <buffer> <enter> :call AirLatex_ProjectEnter() <enter>
      nnoremap <silent> <buffer> d :call AirLatex_ProjectLeave() <enter>
      nnoremap <silent> <buffer> D :call AirLatex_ProjectLeave() <enter>
      autocmd VimLeavePre <buffer> :call AirLatex_Close()
    """)
    return buffer

  @AsyncDecorator
  def _render(self):
    cursor = [0, 0]
    if self.buffer == self.nvim.current.window.buffer:
      cursor = self.nvim.current.window.cursor
      # self.command("setlocal modifiable")

    if self.session:
      projectList = self.session.projectList
    else:
      projectList = []
      self.status = "Starting Session"

    size = self.nvim.eval("g:AirLatexWinSize")
    menu = self.menu.clear(f"AirLatex (ver. {__version__})", size)

    # Display all Projects
    for i, project in enumerate(projectList):

      # skip deleted projects
      if project.get("trashed"):
        continue

      # skip archived projects
      if project.get("archived") and not self.showArchived:
        continue

      # list project structure
      if project.get("open"):
        menu.add_entry(
            f"{self.symbol_open} {project['name']}",
            menu.Item.Project(project),
            indent=1)
        for folder in project.get("rootFolder", [None]):
          self._listProjectStructure([folder], project, menu, indent=3)
      else:
        menu.add_entry(
            f"{self.symbol_closed} {project['name']}",
            menu.Item.Project(project),
            indent=1)

      # if cursor[0] == len(menu.entries):
      #   menu.from_dictionary(
      #       keys=[
      #           ("open", "    -----------------"),
      #           ("msg", "    Status: {}"),
      #           ("await", "    Await: {}"),
      #           ("source", "    Source: {}"),
      #           # Owner is a dictionary
      #           ("owner", "    Owner {firstName}, {lastName}"),
      #           ("lastUpdated", "    {}"),
      #           (("firstName", "lastName"), "    User: {} {}")
      #       ],
      #       data=project)

    # Info
    menu.space(1)
    menu.from_dictionary(
        keys=[
            (
                "status",
                f" Status      : {self.status}",
            ),
            (f" Last Update : {strftime('%H:%M:%S', gmtime())}",),
        ],
        data={})
    self.write()
    if cursor is not None:
      if self.buffer == self.nvim.current.window.buffer:
        self.nvim.current.window.cursor = cursor
    if self.lock.locked():
      self.lock.release()

  @pynvimCatchException
  def _listProjectStructure(self, tree, project, menu, indent=0):
    root = tree[-1]
    if not root:
      menu.add_entry("Unable to load folders")
      return

    for folder in root["folders"]:
      if folder.get("open"):
        menu.add_entry(
            f"{self.symbol_open} {folder['name']}",
            menu.Item.Folder(folder),
            indent=indent)
        self._listProjectStructure(
            tree + [folder], project, menu, indent=indent + 2)
      else:
        menu.add_entry(
            f"{self.symbol_closed} {folder['name']}",
            menu.Item.Folder(folder),
            indent=indent)

    for doc in root["docs"]:
      menu.add_entry(
          doc['name'],
          menu.Item.File(project, tree + [doc], doc),
          indent=indent + 2)

    # list files (other files)
    if root.get("fileRefs"):
      menu.add_entry("file Refs:", indent=indent + 2)
      for file in root["fileRefs"]:
        file["type"] = "fileRef"
        menu.add_entry(f" - {file['name']}", indent=indent + 2)

  @pynvimCatchException
  def registerCursorActions(self, MenuItem, handle):

    @handle(MenuItem.Folder)
    def toggle(folder):
      folder["open"] = not folder.get("open", False)
      Task(self.triggerRefresh())

    @handle(MenuItem.Actions.Disconnect)
    def disconnect():
      if self.session:
        self.session.cleanup()

    @handle(MenuItem.Actions.Retry)
    def retry():
      if self.session:
        Task(self.session.login())

    @handle(MenuItem.Project, "enter")
    def open(project):
      instance = self.session.projects.get(project.get('id'))
      if instance:
        toggle(project)
      else:
        self.log.debug(f"connecting {project}")
        Task(self.session.connectProject(project))

    @handle(MenuItem.Project, "del")
    def close(project):
      instance = self.session.projects.get(project.get('id'))
      if instance:
        # So careful, because project is a shared object. It needs to be
        # shared such that it is stateful in the sidebar. Connected has
        # different implications for being True, False and None. We set it
        # back to None here such that it can properly be set later.
        if project.get("connected"):
          @Task(instance.disconnect).fn()
          async def del_connect(*args):
            if "connected" in project:
              del project["connected"]

    @handle(MenuItem.File)
    def join(project_data, path, doc):
      name = Document.getName(path, project_data)
      for buffer, document in Document.allBuffers.items():
        self.log.debug(f"{name} vs {document.name}")
        if name == document.name:
          self.command('wincmd w')
          self.command(f'buffer {buffer.number}')
          return
      project = self.session.projects.get(project_data.get('id'))

      @Task.Fn()
      async def _join():
        await self.lock.acquire()

        @Task.Fn(vim=True)
        def _callback():
          document = Document(self.nvim, project, path, doc)
          self.log.debug(f"{document.name} Joined")
          self.lock.release()
          Task(project.joinDocument(document))

  def animation(self, name, loop=0.1):
    return Animation(name, self.updateStatus, loop=loop)

  async def updateStatus(self, msg):
    #await self.lock.acquire()
    self.status = msg
    return Task(self.menu.updateEntryByKey, "status",
                self.status)  #.then(self.triggerRefresh)#.then(self.lock.release)
