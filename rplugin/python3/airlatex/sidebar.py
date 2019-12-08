import pynvim
from time import gmtime, strftime
from threading import Thread, Lock
from airlatex.documentbuffer import DocumentBuffer
from airlatex.util import getLogger
import traceback


import traceback
def catchException(fn):
    def wrapped(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except Exception as e:
            self.log.error(str(e))
            # nvim.err_write(traceback.format_exc(e)+"\n")
            self.nvim.err_write(str(e)+"\n")
    return wrapped

class SideBar:
    def __init__(self, nvim, airlatex):
        self.nvim = nvim
        self.servername = self.nvim.eval("v:servername")
        self.airlatex = airlatex
        self.lastUpdate = gmtime()
        self.buffer = None
        self.buffer_write_i = 0
        self.buffer_mutex = Lock()
        self.cursorPos = []
        self.log = getLogger(__name__)
        self.log.debug("SideBar initialized.")

        self.symbol_open=self.nvim.eval("g:AirLatexArrowOpen")
        self.symbol_closed=self.nvim.eval("g:AirLatexArrowClosed")

    @catchException
    def cleanup(self):
        self.airlatex.session.cleanup(self.nvim)


    # ----------- #
    # GUI Drawing #
    # ----------- #

    @catchException
    def triggerRefresh(self):
        self.log.debug("triggerRefresh()")
        self.listProjects(overwrite=True)

    @catchException
    def updateStatus(self):
        if self.airlatex.session:
            self.log.debug("updateStatus()")
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
        if self.buffer == self.nvim.current.buffer:
            cursorPos = self.nvim.current.window.cursor[0]
            if self.buffer_write_i == cursorPos:
                self.cursorPos = pos

    @catchException
    def vimCursorSet(self,row,col):
        if self.buffer == self.nvim.current.buffer:
            window = self.nvim.current.window
            window.cursor = (row,col)

    @catchException
    def initGUI(self):
        self.log.debug("initGUI()")
        self.initSidebarBuffer()
        self.listProjects()

    @catchException
    def initSidebarBuffer(self):
        self.log.debug("initSidebarBuffer()")

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
        self.nvim.command('setlocal nowrap')
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

    @catchException
    def listProjects(self, overwrite=False):
        self.log.debug("listProjects(%s)" % str(overwrite))
        self.buffer_mutex.acquire()
        self.log.debug("listProjects -> mutex locked")
        try:
            # self.nvim.command('setlocal ma')
            self.cursorPos = []
            if self.airlatex.session:
                projectList = self.airlatex.session.projectList(self.nvim)
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
            if not overwrite:
                self.vimCursorSet(5,1)
            del(self.buffer[self.buffer_write_i:len(self.buffer)])
            # self.nvim.command('setlocal noma')
        except Exception as e:
            self.log.error(traceback.format_exc(e))
            self.nvim.err_write(traceback.format_exc(e)+"\n")
        finally:
            self.buffer_mutex.release()
            self.log.debug("listProjects -> mutex released")

    @catchException
    def listProjectStructure(self, rootFolder, pos, indent=0):
        self.log.debug("listProjectStructure()")

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
        self.log.debug("cursorAction(%s)" % key)

        if not isinstance(self.cursorPos, list):
            pass

        elif len(self.cursorPos) == 0:
            pass

        elif len(self.cursorPos) == 1:
            project = self.cursorPos[0]
            if "handler" in project:
                if key == "enter":
                    self._toggle(self.cursorPos[-1], "open", default=False)
                elif key == "d":
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








