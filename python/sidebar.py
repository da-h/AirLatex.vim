import vim
from time import gmtime, strftime, sleep
from threading import Thread, Lock
import os
import sys
sys.path.insert(0, vim.eval("s:airlatex_home"))
from python.session import AirLatexSession


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

from difflib import SequenceMatcher

if "allBuffers" not in globals():
    allBuffers = {}
class DocumentBuffer:

    def __init__(self, path):
        self.path = path
        self.project_handler = path[0]["handler"]
        self.document = path[-1]
        self.initDocumentBuffer()
        self.buffer_mutex = Lock()
        self.saved_buffer = None

    def getName(self):
        return "/".join([p["name"] for p in self.path])
    def getExt(self):
        return self.document["name"].split(".")[-1]

    def initDocumentBuffer(self):

        # Creating new Buffer
        vim.command('wincmd w')
        vim.command('enew')
        vim.command('file '+self.getName())
        self.buffer = vim.current.buffer
        allBuffers[self.buffer] = self

        # Buffer Settings
        vim.command("syntax on")
        vim.command('setlocal noswapfile')
        vim.command('setlocal buftype=nofile')
        vim.command("set filetype="+self.getExt())

        # self.applyString(serverBuffer)

        # ??? Returning normal function to these buttons
        # vim.command("nmap <silent> <up> <up>")
        # vim.command("nmap <silent> <down> <down>")
        # vim.command("nmap <silent> <enter> <enter>")
        # vim.command("set updatetime=500")
        # vim.command("autocmd CursorMoved,CursorMovedI * :call AirLatex_update_pos()")
        # vim.command("autocmd CursorHold,CursorHoldI * :call AirLatex_update_pos()")
        vim.command("au CursorMoved <buffer> call AirLatex_writeBuffer()")
        vim.command("au CursorMovedI <buffer> call AirLatex_writeBuffer()")
        vim.command("command! -buffer -nargs=0 W call AirLatex_writeBuffer()")

    def write(self, lines):
        def writeLines(buffer,lines):
            buffer[0] = lines[0]
            for l in lines[1:]:
                buffer.append(l)
            self.saved_buffer = buffer[:]
        # self.serverBuffer = "\n".join(lines)
        vim.async_call(writeLines,self.buffer,lines)

    def writeBuffer(self):

        # skip if not yet initialized
        if self.saved_buffer is None:
            return

        # nothing to do
        if len(self.saved_buffer) == len(self.buffer):
            skip = True
            for ol,nl in zip(self.saved_buffer, self.buffer):
                if hash(ol) != hash(nl):
                    skip = False
                    break
            if skip:
                return

        # calculate diff
        old = "\n".join(self.saved_buffer)
        new = "\n".join(self.buffer)
        S = SequenceMatcher(None, old, new, autojunk=False).get_opcodes()
        ops = []
        for op in S:
            if op[0] == "equal":
                continue

            elif op[0] == "replace":
                ops.append({"p": op[1], "i": new[op[3]:op[4]]})
                ops.append({"p": op[1], "d": old[op[1]:op[2]]})

            elif op[0] == "insert":
                ops.append({"p": op[1], "i": new[op[3]:op[4]]})

            elif op[0] == "delete":
                ops.append({"p": op[1], "d": old[op[1]:op[2]]})

        # nothing to do
        if len(ops) == 0:
            return

        # reverse, as last op should be applied first
        ops.reverse()

        # update saved buffer & send command
        self.saved_buffer = self.buffer[:]
        self.project_handler.sendOps(self.document, ops)

    def applyUpdate(self,ops):

        # adapt version
        if "v" in ops:
            v = ops["v"]
            if v > self.document["version"]:
                self.document["version"] = v

        # do nothing if no op included
        if not 'op' in ops:
            return
        ops = ops['op']

        # async execution
        def applyOps(self, ops):
            self.buffer_mutex.acquire()
            try:
                for op in ops:

                    # delete char and lines
                    if 'd' in op:
                        p = op['p']
                        s = op['d']
                        self._remove(self.buffer,p,s)
                        self._remove(self.saved_buffer,p,s)

                    # add characters and newlines
                    if 'i' in op:
                        p = op['p']
                        s = op['i']
                        self._insert(self.buffer,p,s)
                        self._insert(self.saved_buffer,p,s)
            finally:
                self.buffer_mutex.release()
        vim.async_call(applyOps, self, ops)

    # inster string at given position
    def _insert(self, buffer, start, string):
        p_linestart = 0

        # find start line
        for line_i, line in enumerate(self.buffer):

            # start is not yet there
            if start >= p_linestart+len(line)+1:
                p_linestart += len(line)+1
            else:
                break

        # convert format to array-style
        string = string.split("\n")

        # append end of current line to last line of new line
        string[-1] += line[(start-p_linestart):]

        # include string at start position
        buffer[line_i] = line[:(start-p_linestart)] + string[0]

        # append rest to next line
        if len(string) > 1:
            buffer[line_i+1:line_i+1] = string[1:]

    # remove len chars from pos
    def _remove(self, buffer, start, string):
        p_linestart = 0

        # find start line
        for line_i, line in enumerate(buffer):

            # start is not yet there
            if start >= p_linestart+len(line)+1:
                p_linestart += len(line)+1
            else:
                break

        # convert format to array-style
        string = string.split("\n")
        new_string = ""

        # remove first line from found position
        new_string = line[:(start-p_linestart)]

        # add rest of last line to new string
        if len(string) == 1:
            new_string += buffer[line_i+len(string)-1][(start-p_linestart)+len(string[-1]):]
        else:
            new_string += buffer[line_i+len(string)-1][len(string[-1]):]

        # overwrite buffer
        buffer[line_i:line_i+len(string)] = [new_string]









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
    if buffer in allBuffers:
        allBuffers[buffer].writeBuffer()
