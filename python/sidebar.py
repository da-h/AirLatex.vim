import vim
import sys
from time import gmtime, strftime
from threading import Thread, Lock
sys.path.insert(0, vim.eval("s:airlatex_home"))
from python.session import AirLatexSession
from python.documentbuffer import DocumentBuffer


class SideBar:
    def __init__(self):
        self.session = None
        self.lastUpdate = gmtime()
        self.buffer = None
        self.buffer_write_i = 0
        self.buffer_mutex = Lock()
        self.cursorPos = []

        self.symbol_open=vim.eval("g:AirLatexArrowOpen")
        self.symbol_closed=vim.eval("g:AirLatexArrowClosed")

        # Setup GUI & Session
        self.initGUI()
        DOMAIN = vim.eval("g:airlatex_domain")
        print(DOMAIN)
        def initSession(self):
            self.session = AirLatexSession(DOMAIN, self)
            self.session.login()
            self.triggerRefresh()
        self.session_thread = Thread(target=initSession,args=(self,), daemon=True)
        self.session_thread.start()

    def cleanup(self):
        self.session.cleanup()
        self.session_thread.stop()


    # ----------- #
    # GUI Drawing #
    # ----------- #

    def triggerRefresh(self):
        def refresh():
            self.listProjects(overwrite=True)
        if not sidebar.buffer_mutex.locked():
            vim.async_call(refresh)

    def bufferappend(self, arg, pos=[]):
        if self.buffer_write_i >= len(self.buffer):
            self.buffer.append(arg)
        else:
            self.buffer[self.buffer_write_i] = arg
        self.buffer_write_i += 1
        cursorPos = vim.current.window.cursor[0]
        if self.buffer_write_i == cursorPos:
            self.cursorPos = pos

    def vimCursorSet(self,row,col):
        window = vim.current.window
        window.cursor = (row,col)

    def initGUI(self):
        self.initSidebarBuffer()
        self.listProjects()

    def initSidebarBuffer(self):
        vim.command('let splitLocation = g:AirLatexWinPos ==# "left" ? "topleft " : "botright "')
        vim.command('let splitSize = g:AirLatexWinSize')

        vim.command("""
            silent! exec splitLocation . 'vertical ' . splitSize . ' new'
            silent! exec "buffer " . "AirLatex"
        """)

        vim.command('file AirLatex')
        vim.command('setlocal winfixwidth')

        # throwaway buffer options (thanks NERDTree)
        vim.command('setlocal noswapfile')
        vim.command('setlocal buftype=nofile')
        vim.command('setlocal bufhidden=hide')
        vim.command('setlocal nowrap')
        vim.command('setlocal foldcolumn=0')
        vim.command('setlocal foldmethod=manual')
        vim.command('setlocal nofoldenable')
        vim.command('setlocal nobuflisted')
        vim.command('setlocal nospell')
        vim.command('setlocal nonu')
        vim.command('setlocal nornu')
        vim.command('iabc <buffer>')
        vim.command('setlocal cursorline')
        vim.command('setlocal filetype=airlatex')
        self.buffer = vim.current.buffer

        # Register Mappings
        vim.command("nmap <silent> <buffer> q :q <enter>")
        vim.command("nmap <silent> <buffer> <up> <up> <bar> :call AirLatex_project_update() <enter> <bar> <right>")
        vim.command("nmap <silent> <buffer> k <up> <bar> :call AirLatex_project_update() <enter> <bar> <right>")
        vim.command("nmap <silent> <buffer> <down> <down> <bar> :call AirLatex_project_update() <enter> <bar> <right>")
        vim.command("nmap <silent> <buffer> j <down> <bar> :call AirLatex_project_update() <enter> <bar> <right>")
        vim.command("nmap <silent> <enter> :call AirLatex_project_enter() <enter>")
        vim.command("autocmd VimLeavePre <buffer> :call AirLatex_close()")



    def listProjects(self, overwrite=False):
        self.buffer_mutex.acquire()
        try:
            vim.command('setlocal ma')
            self.cursorPos = []
            if self.session:
                projectList = self.session.projectList()
                status = self.session.status
            else:
                projectList = []
                status = "Connecting ..."

            # Display Header
            if not overwrite:
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
                        if "msg" in project:
                            self.bufferappend("   msg: "+project['msg'])
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
            self.bufferappend(" Last Update : "+strftime("%H:%M:%S",self.lastUpdate), ["lastupdate"])
            if not overwrite:
                self.vimCursorSet(5,1)
            del(vim.current.buffer[self.buffer_write_i:len(vim.current.buffer)])
            vim.command('setlocal noma')
        finally:
            self.buffer_mutex.release()

    def listProjectStructure(self, rootFolder, pos, indent=0):

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


    def cursorAction(self, key="enter"):
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
                self.session.connectProject(project)

        elif not isinstance(self.cursorPos[-1], dict):
            pass

        # is folder
        elif self.cursorPos[-1]["type"] == "folder":
            self._toggle(self.cursorPos[-1], "open")
            self.triggerRefresh()

        # is file
        elif self.cursorPos[-1]["type"] == "file":
            documentbuffer = DocumentBuffer(self.cursorPos)
            self.cursorPos[0]["handler"].joinDocument(documentbuffer)


    def _toggle(self, dict, key, default=True):
        if key not in dict:
            dict[key] = default
        else:
            dict[key] = not dict[key]








cmd = vim.eval("g:cmd")
if cmd == "start":
    if "sidebar" in globals():
        sidebar.initGUI()
    else:
        sidebar = SideBar()
elif cmd == "update":
    if not sidebar.buffer_mutex.locked():
        sidebar.triggerRefresh()
elif cmd=="enter":
    sidebar.cursorAction()
elif cmd=="d":
    sidebar.cursorAction(key="d")
# elif cmd=="updatePos":
#     plugin.updateProject()
elif cmd=="close":
    sidebar.cleanup()
    sidebar = None
elif cmd=="writeBuffer":
    buffer = vim.current.buffer
    if buffer in DocumentBuffer.allBuffers:
        DocumentBuffer.allBuffers[buffer].writeBuffer()
