import pynvim
from time import gmtime, strftime
from threading import Thread, currentThread
from asyncio import Queue, Lock
from airlatex.documentbuffer import DocumentBuffer
from airlatex.util import getLogger
import traceback


import traceback
def catchException(fn):
    def wrapped(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except Exception as e:
            # self.log.error(str(e))
            # self.nvim.err_write(str(e)+"\n")
            self.log.exception(str(e))
    return wrapped

class SideBar:
    def __init__(self, nvim, airlatex):
        self.nvim = nvim
        self.servername = self.nvim.eval("v:servername")
        self.airlatex = airlatex
        self.lastUpdate = gmtime()
        self.buffer = None
        self.buffer_write_i = 0
        self.cursorPos = []
        self.log = getLogger(__name__)
        self.log.debug_gui("SideBar initialized.")
        self.cursor = (4,0)
        self.refresh_queue = Queue()
        self.refresh_lock = Lock()

        self.symbol_open=self.nvim.eval("g:AirLatexArrowOpen")
        self.symbol_closed=self.nvim.eval("g:AirLatexArrowClosed")

        self.nvim.loop.create_task(self.flush_refresh())

    @catchException
    def cleanup(self):
        # self.refresh_thread.do_run = False
        self.airlatex.session.cleanup(self.nvim)


    # ----------- #
    # GUI Drawing #
    # ----------- #

    # @catchException
    async def flush_refresh(self):
        try:
            self.log.debug_gui("flush_refresh() -> started loop")

            # direct sending
            while True:
                arg = await self.refresh_queue.get()
                self.log.debug("flush_refresh() -> called")

                # flush also all other waiting triggerRefresh-Calls
                num = self.refresh_queue.qsize()
                for i in range(num):
                    arg = await self.refresh_queue.get()

                # in case something happend during drawing
                # if num > 0:
                #     self.refresh_queue.put(True)

                await self.refresh_lock.acquire()
                self.nvim.async_call(self.listProjects, (True))
                # await self.refresh_lock.release()
        except Exception as e:
            self.log.exception(str(e))

    @catchException
    async def triggerRefresh(self):
        self.log.debug("triggerRefresh() -> event called")
        await self.refresh_queue.put(True)

    @catchException
    def updateStatus(self):
        if self.airlatex.session and hasattr(self,'statusline'):
            self.log.debug_gui("updateStatus()")
            # self.nvim.command('setlocal ma')
            self.statusline[0] = self.statusline[0][:15] + self.airlatex.session.status
            # self.nvim.command('setlocal noma')

    @catchException
    def bufferappend(self, arg, pos=[]):
        if self.buffer_write_i >= len(self.buffer):
            self.buffer.append(arg)
        else:
            self.buffer[self.buffer_write_i] = arg
        self.buffer_write_i += 1
        if self.buffer_write_i == self.cursor[0]:
            self.cursorPos = pos

    @catchException
    def vimCursorSet(self,row,col):
        if self.buffer == self.nvim.current.window.buffer:
            window = self.nvim.current.window
            window.cursor = (row,col)

    @catchException
    def initGUI(self):
        self.log.debug_gui("initGUI()")
        self.initSidebarBuffer()
        self.refresh_queue.put(False)
        self.listProjects(False)
        # self.nvim.async_call(self.listProjects, (False))
        # self.nvim.loop.create_task(self.listProjects(False))

    @catchException
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
        self.nvim.command("nmap <silent> <buffer> q :q <enter>")
        self.nvim.command("nmap <silent> <buffer> <up> <up> <bar> :call AirLatex_SidebarRefresh() <enter> <bar> <right>")
        self.nvim.command("nmap <silent> <buffer> k <up> <bar> :call AirLatex_SidebarRefresh() <enter> <bar> <right>")
        self.nvim.command("nmap <silent> <buffer> <down> <down> <bar> :call AirLatex_SidebarRefresh() <enter> <bar> <right>")
        self.nvim.command("nmap <silent> <buffer> j <down> <bar> :call AirLatex_SidebarRefresh() <enter> <bar> <right>")
        self.nvim.command("nmap <silent> <enter> :call AirLatex_ProjectEnter() <enter>")
        self.nvim.command("autocmd VimLeavePre <buffer> :call AirLatex_Close()")
        self.nvim.command("nmap <silent> <buffer> d :call AirLatex_ProjectLeave() <enter>")
        self.nvim.command("nmap <silent> <buffer> D :call AirLatex_ProjectLeave() <enter>")

    @catchException
    def listProjects(self, overwrite=False):
        self.log.debug_gui("listProjects(%s)" % str(overwrite))
        if self.buffer == self.nvim.current.window.buffer:
            self.cursor = self.nvim.current.window.cursor
        try:
            # self.nvim.command('setlocal ma')
            self.cursorPos = []
            if self.airlatex.session:
                projectList = self.airlatex.session.projectList()
                status = self.airlatex.session.status
            else:
                projectList = []
                status = "Starting Session"

            # Display Header
            if not overwrite or True:
                self.buffer_write_i = 0
                self.bufferappend("  ")
                self.bufferappend(" AirLatex")
                self.bufferappend(" ========")
                self.bufferappend("  ")
            else:
                self.buffer_write_i = 4

            # Display all Projects
            if projectList is not None:
                for i,project in enumerate(projectList):
                    pos = [project]

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
                    if "msg" in project and ("connected" in project and project["connected"] or self.cursorAt([project])):
                        self.bufferappend("   msg: "+project['msg'])
                    if self.cursorAt([project]):
                        self.bufferappend("   awaits: "+("↑" if "await" not in project or not project["await"] else "↓"))
                        self.bufferappend("   source: "+project['source'])
                        self.bufferappend("   owner: "+project['owner']['first_name']+" "+project['owner']['last_name'])
                        self.bufferappend("   last change: "+project['lastUpdated'])
                        if "lastUpdatedBy" in project:
                            self.bufferappend("    -> by: "+project['lastUpdatedBy']['first_name']+" "+project['lastUpdatedBy']['last_name'])

            # Info
            self.bufferappend("  ")
            self.bufferappend("  ")
            self.bufferappend("  ")
            self.bufferappend(" Status      : %s" % status, ["status"])
            self.statusline = self.buffer.range(self.buffer_write_i, self.buffer_write_i+1)
            self.updateStatus()
            self.bufferappend(" Last Update : "+strftime("%H:%M:%S",self.lastUpdate), ["lastupdate"])
            self.bufferappend(" Quit All    : enter", ["disconnect"])
            if not overwrite:
                self.vimCursorSet(5,1)
            del(self.buffer[self.buffer_write_i:len(self.buffer)])
            # self.nvim.command('setlocal noma')
        except Exception as e:
            self.log.error(traceback.format_exc(e))
            self.nvim.err_write(traceback.format_exc(e)+"\n")
        finally:
            self.nvim.loop.create_task(self._refresh_lock_release())

    async def _refresh_lock_release(self):
        await self.refresh_lock.release()

    @catchException
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

    @catchException
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


    @catchException
    def cursorAction(self, key="enter"):
        self.log.debug_gui("cursorAction(%s)" % key)

        if not isinstance(self.cursorPos, list):
            pass

        elif len(self.cursorPos) == 0:
            pass

        elif len(self.cursorPos) == 1:
            # disconnect all
            if self.cursorPos[0] == "disconnect":
                if self.airlatex.session:
                    self.airlatex.session.cleanup(self.nvim)

            # else is project
            elif not isinstance(self.cursorPos[0], str):
                project = self.cursorPos[0]
                if "handler" in project:
                    if key == "enter":
                        self._toggle(self.cursorPos[-1], "open", default=False)
                    elif key == "del":
                        if "connected" in project and project["connected"]:
                            project["handler"].disconnect()
                    self.triggerRefresh()
                else:
                    self.airlatex.session.connectProject(self.nvim, project)

        elif not isinstance(self.cursorPos[-1], dict):
            pass

        # is folder
        elif self.cursorPos[-1]["type"] == "folder":
            self._toggle(self.cursorPos[-1], "open")
            self.triggerRefresh()

        # is file
        elif self.cursorPos[-1]["type"] == "file":
            documentbuffer = DocumentBuffer(self.cursorPos, self.nvim)
            self.cursorPos[0]["handler"].joinDocument(documentbuffer)

    @catchException
    def _toggle(self, dict, key, default=True):
        if key not in dict:
            dict[key] = default
        else:
            dict[key] = not dict[key]








