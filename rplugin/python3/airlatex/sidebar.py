import pynvim
from time import gmtime, strftime
from asyncio import Queue, Lock, sleep, create_task
from airlatex.documentbuffer import DocumentBuffer
from logging import getLogger, NOTSET
from airlatex.util import __version__, pynvimCatchException



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
        self.log.debug_gui("SideBar initialized.")
        self.cursor = (2,0)

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
        self.nvim.async_call(self.listProjects, all)

    async def updateStatus(self, msg):
        self.log.debug_gui("trying to acquire (in update)")
        await self.uilock.acquire()
        self.status = msg
        self.log.debug_gui("updateStatus()")
        self.nvim.async_call(self.updateStatusLine)



    # ----------- #
    # GUI Drawing #
    # ----------- #

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
        self.initSidebarBuffer()
        create_task(self.uilock.acquire())
        self._listProjects(False)

    @pynvimCatchException
    def initSidebarBuffer(self):
        self.log.debug_gui("initSidebarBuffer()")

        self.nvim.command('let splitLocation = g:AirLatexWinPos ==# "left" ? "topleft " : "botright "')
        self.nvim.command('let splitSize = g:AirLatexWinSize')

        self.nvim.command("""
            silent! exec splitLocation . 'vertical ' . splitSize . ' new'
            silent! exec "buffer " . "AirLatex"
        """)

        self.buffer = self.nvim.current.buffer

        self.nvim.command('file AirLatex')
        self.nvim.command('setlocal winfixwidth')

        # throwaway buffer options (thanks NERDTree)
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
        self.nvim.command('setlocal filetype=airlatex')

        # Register Mappings
        self.nvim.command("nnoremap <silent> <buffer> q :q <enter>")
        self.nvim.command("nnoremap <silent> <buffer> <up> <up> <bar> :call AirLatex_SidebarRefresh() <enter> <bar> <right>")
        self.nvim.command("nnoremap <silent> <buffer> k <up> <bar> :call AirLatex_SidebarRefresh() <enter> <bar> <right>")
        self.nvim.command("nnoremap <silent> <buffer> <down> <down> <bar> :call AirLatex_SidebarRefresh() <enter> <bar> <right>")
        self.nvim.command("nnoremap <silent> <buffer> j <down> <bar> :call AirLatex_SidebarRefresh() <enter> <bar> <right>")
        self.nvim.command("nnoremap <silent> <enter> :call AirLatex_ProjectEnter() <enter>")
        self.nvim.command("autocmd VimLeavePre <buffer> :call AirLatex_Close()")
        self.nvim.command("nnoremap <silent> <buffer> d :call AirLatex_ProjectLeave() <enter>")
        self.nvim.command("nnoremap <silent> <buffer> D :call AirLatex_ProjectLeave() <enter>")

    @pynvimCatchException
    def listProjects(self, overwrite=False):
        self._listProjects(overwrite)

    def _listProjects(self, overwrite=False):
        self.log.debug_gui("listProjects(%s)" % str(overwrite))
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
        if not overwrite or True:
            self.buffer_write_i = 0
            self.bufferappend("   ┄┄┄┄┄┄ AirLatex (ver %s) ┄┄┄┄┄┄┄ " % __version__)
            self.bufferappend(" ")
        else:
            self.buffer_write_i = 4

        # Display all Projects
        if projectList is not None:
            for i,project in enumerate(projectList):
                pos = [project]

                # skip deleted projects
                if "trashed" in project and project["trashed"]:
                    continue

                # skip archived projects
                if "archived" in project and project["archived"] and not self.showArchived:
                    continue

                # list project structure
                if "open" in project and project["open"]:
                    self.bufferappend(" "+self.symbol_open+" "+project["name"], pos)
                    self.listProjectStructure(project["rootFolder"][0], pos)
                else:
                    self.bufferappend(" "+self.symbol_closed+" "+project["name"], pos)

                # cursor-over info
                if self.cursorAt([project]):
                    if "open" in project and project["open"]:
                        self.bufferappend("   -----------------")
                if "msg" in project and ("connected" in project and project["connected"] or self.cursorAt([project]) or "msg" in project and project["msg"].startswith("Error")):
                    if project["msg"].startswith("Error: "):
                        self.bufferappend("   error: "+project['msg'][7:])
                    else:
                        self.bufferappend("   msg: "+project['msg'])
                if self.cursorAt([project]):
                    if "await" not in project:
                        self.bufferappend("   awaits: [enter to connect]")
                    else:
                        self.bufferappend("   awaits: "+("↑" if not project["await"] else "↓"))
                    if "source" in project:
                        self.bufferappend("   source: "+project['source'])
                    if "owner" in project:
                        self.bufferappend("   owner: "+project['owner']['first_name']+(" "+project['owner']['last_name'] if "last_name" in project["owner"] else ""))
                    if "lastUpdated" in project:
                        self.bufferappend("   last change: "+project['lastUpdated'])
                    if "lastUpdatedBy" in project:
                        self.bufferappend("    -> by: "+project['lastUpdatedBy']['first_name']+" "+(" "+project['lastUpdatedBy']['last_name'] if "last_name" in project["lastUpdatedBy"] else ""))

        # Info
        self.bufferappend("  ")
        self.bufferappend("  ")
        self.bufferappend("  ")
        self.bufferappend(" Retry       : enter", ["retry"])
        self.bufferappend(" Status      : %s" % self.status, ["status"])
        self.statusline = self.buffer.range(self.buffer_write_i, self.buffer_write_i+1)
        self.updateStatusLine(releaseLock=False)
        self.bufferappend(" Last Update : "+strftime("%H:%M:%S",self.lastUpdate), ["lastupdate"])
        self.bufferappend(" Quit All    : enter", ["disconnect"])
        if not overwrite:
            self.vimCursorSet(3,1)
        del(self.buffer[self.buffer_write_i:len(self.buffer)])
        # self.nvim.command('setlocal noma')

        if self.uilock.locked():
            self.uilock.release()

    @pynvimCatchException
    def listProjectStructure(self, rootFolder, pos, indent=0):
        self.log.debug_gui("listProjectStructure()")

        # list folders first
        indentStr = "   "+"  "*indent
        for folder in rootFolder["folders"]:
            folder["type"] = "folder"
            if "open" in folder and folder["open"]:
                self.bufferappend(indentStr+self.symbol_open+" "+folder["name"], pos+[folder])
                self.listProjectStructure(folder, pos+[folder], indent+1)
            else:
                self.bufferappend(indentStr+self.symbol_closed+" "+folder["name"], pos+[folder])

        # list editable files
        indentStr = "   "+"  "*(indent+1)
        for doc in rootFolder["docs"]:
            doc["type"] = "file"
            self.bufferappend(indentStr+doc["name"], pos+[doc])

        # list files (other files)
        if len(rootFolder["fileRefs"]) > 0:
            self.bufferappend("   file Refs:", pos+["fileRefs"])
            for file in rootFolder["fileRefs"]:
                file["type"] = "fileRef"
                self.bufferappend("    - "+file["name"], pos+[file])


    # ------- #
    # Actions #
    # ------- #

    @pynvimCatchException
    def _toggle(self, dict, key, default=True):
        if key not in dict:
            dict[key] = default
        else:
            dict[key] = not dict[key]

    @pynvimCatchException
    def vimCursorSet(self,row,col):
        if self.buffer == self.nvim.current.window.buffer:
            window = self.nvim.current.window
            window.cursor = (row,col)

    @pynvimCatchException
    def cursorAt(self, pos):

        # no pos given
        if not isinstance(pos,list):
            return False

        # cannot be at same position (pos is specified in more detail)
        if len(pos) > len(self.cursorPos):
            return False

        # check if all positions match
        for p,c in zip(pos,self.cursorPos):
            if p != c:
                return False
        return True


    @pynvimCatchException
    def cursorAction(self, key="enter"):
        if not isinstance(self.cursorPos, list):
            return
        self.log.debug_gui("cursorAction(%s) on %s" % (key, ",".join(str(p) for p in self.cursorPos)))

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
                    create_task(self.airlatex.session.login())

            # else is project
            elif not isinstance(self.cursorPos[0], str):
                project = self.cursorPos[0]
                if "handler" in project:
                    if key == "enter":
                        self._toggle(self.cursorPos[-1], "open", default=False)
                    elif key == "del":
                        if "connected" in project and project["connected"]:
                            project["handler"].disconnect()
                    create_task(self.triggerRefresh())
                else:
                    create_task(self.airlatex.session.connectProject(project))

        elif not isinstance(self.cursorPos[-1], dict):
            pass

        # is folder
        elif self.cursorPos[-1]["type"] == "folder":
            self._toggle(self.cursorPos[-1], "open")
            create_task(self.triggerRefresh())

        # is file
        elif self.cursorPos[-1]["type"] == "file":
            documentbuffer = DocumentBuffer(self.cursorPos, self.nvim)
            create_task(self.cursorPos[0]["handler"].joinDocument(documentbuffer))








