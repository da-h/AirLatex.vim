import pynvim
from difflib import SequenceMatcher
from threading import RLock
from hashlib import sha1
from asyncio import create_task
from logging import getLogger

if "allBuffers" not in globals():
    allBuffers = {}
class DocumentBuffer:
    allBuffers = allBuffers

    def __init__(self, path, nvim):
        self.log = getLogger("AirLatex")
        self.path = path
        self.nvim = nvim
        self.project_handler = path[0]["handler"]
        self.document = path[-1]
        self.initDocumentBuffer()
        self.buffer_mutex = RLock()
        self.saved_buffer = None
        self.locally_saved = False

    def getName(self):
        return "/".join([p["name"] for p in self.path])
    def getExt(self):
        return self.document["name"].split(".")[-1]

    def initDocumentBuffer(self):
        self.log.debug_gui("initDocumentBuffer")

        # Creating new Buffer
        self.nvim.command('wincmd w')
        self.nvim.command('enew')
        self.nvim.command('file '+self.getName())
        self.buffer = self.nvim.current.buffer
        DocumentBuffer.allBuffers[self.buffer] = self

        # Buffer Settings
        normal_buftype = self.nvim.eval("g:AirLatexBuftype") == 'NORMAL'
        buftype = 'nofile'
        if normal_buftype:
            buftype = ''
        self.nvim.command("syntax on")
        self.nvim.command('setlocal noswapfile')
        self.nvim.command('setlocal buftype='+buftype)
        self.nvim.command("set filetype="+self.getExt())

        # ??? Returning normal function to these buttons
        # self.nvim.command("nmap <silent> <up> <up>")
        # self.nvim.command("nmap <silent> <down> <down>")
        # self.nvim.command("nmap <silent> <enter> <enter>")
        # self.nvim.command("set updatetime=500")
        # self.nvim.command("autocmd CursorMoved,CursorMovedI * :call AirLatex_update_pos()")
        # self.nvim.command("autocmd CursorHold,CursorHoldI * :call AirLatex_update_pos()")
        self.nvim.command("au CursorMoved <buffer> call AirLatex_WriteBuffer()")
        self.nvim.command("au CursorMovedI <buffer> call AirLatex_WriteBuffer()")
        self.nvim.command("command! -buffer -nargs=0 W call AirLatex_WriteBuffer()")
        if normal_buftype:
            self.nvim.command("au BufWritePre <buffer> call AirLatex_WriteLocalBufferPre()")

    def write(self, lines):
        self.log.debug("writing to buffer")

        def writeLines(buffer,lines):
            buffer[0] = lines[0]
            for l in lines[1:]:
                buffer.append(l)
            self.saved_buffer = buffer[:]
        self.nvim.async_call(writeLines,self.buffer,lines)

    def updateRemoteCursor(self, cursor):
        self.log.debug("updateRemoteCursor")
        # def updateRemoteCursor(cursor, nvim):
        #     nvim.command("match ErrorMsg #\%"+str(cursor["row"])+"\%"+str(cursor["column"])+"v#")
        # self.nvim.async_call(updateRemoteCursor, cursor, self.nvim)

    def writeBuffer(self):
        self.log.debug("writeBuffer: calculating changes to send")

        # update CursorPosition
        create_task(self.project_handler.updateCursor(self.document, self.nvim.current.window.cursor))

        # skip if not yet initialized
        if self.saved_buffer is None:
            self.log.debug("writeBuffer: -> buffer not yet initialized")
            return

        # nothing to do
        if len(self.saved_buffer) == len(self.buffer):
            skip = True
            for ol,nl in zip(self.saved_buffer, self.buffer):
                if hash(ol) != hash(nl):
                    skip = False
                    break
            if skip:
                self.log.debug("writeBuffer: -> done (hashtest says nothing to do)")
                return

        # cummulative position of line
        pos = [0]
        for row in self.saved_buffer:
            # pos.append(pos[-1]+ ( len(row)+1 if len(row) > 0 else 0 ) )
            pos.append(pos[-1]+len(row)+1)

        # first calculate diff row-wise
        ops = []
        S = SequenceMatcher(None, self.saved_buffer, self.buffer, autojunk=False).get_opcodes()
        for op in S:
            if op[0] == "equal":
                continue

            # inserting a whole row
            elif op[0] == "insert":
                s = "\n".join(self.buffer[op[3]:op[4]])
                if op[1] >= len(self.saved_buffer):
                    p = pos[-1] - 1
                    s = "\n" + s
                else:
                    p = pos[op[1]]
                    s = s + "\n"
                ops.append({"p": p, "i": s})

            # deleting a whole row
            elif op[0] == "delete":
                s = "\n".join(self.saved_buffer[op[1]:op[2]])
                if op[1] == len(self.buffer):
                    p = pos[-(op[2]-op[1])-1] - 1
                    s = "\n" + s
                else:
                    p = pos[op[1]]
                    s = s + "\n"
                ops.append({"p": p , "d": s})

            # for replace, check in more detail what has changed
            elif op[0] == "replace":
                old = "\n".join(self.saved_buffer[op[1]:op[2]])
                new = "\n".join(self.buffer[op[3]:op[4]])
                S2 = SequenceMatcher(None, old, new, autojunk=False).get_opcodes()
                for op2 in S2:
                    # relative to document end
                    linestart = pos[op[1]]

                    if op2[0] == "equal":
                        continue

                    elif op2[0] == "replace":
                        ops.append({"p": linestart + op2[1], "i": new[op2[3]:op2[4]]})
                        ops.append({"p": linestart + op2[1], "d": old[op2[1]:op2[2]]})

                    elif op2[0] == "insert":
                        ops.append({"p": linestart + op2[1], "i": new[op2[3]:op2[4]]})

                    elif op2[0] == "delete":
                        ops.append({"p": linestart + op2[1], "d": old[op2[1]:op2[2]]})

        # nothing to do
        if len(ops) == 0:
            self.log.debug("writeBuffer: -> done (sequencematcher says nothing to do)")
            return

        # reverse, as last op should be applied first
        ops.reverse()

        # compute sha1-hash of current buffer
        buffer_cpy = self.buffer[:]
        current_len = 0
        for row in buffer_cpy:
            current_len += len(row)+1
        current_len -= 1
        tohash = ("blob "+str(current_len) + "\x00")
        for b in buffer_cpy[:-1]:
            tohash += b+"\n"
        tohash += buffer_cpy[-1]
        sha = sha1()
        sha.update(tohash.encode())
        content_hash = sha.hexdigest()

        # update saved buffer & send command
        self.saved_buffer = self.buffer[:]
        self.log.debug(" -> sending ops")
        create_task(self.project_handler.sendOps(self.document, content_hash, ops))

    def applyUpdate(self,ops):
        self.log.debug("apply server updates to buffer")

        # adapt version
        if "v" in ops:
            v = ops["v"]
            if v >= self.document["version"]:
                self.document["version"] = v+1

        # do nothing if no op included
        if not 'op' in ops:
            return
        self.log.debug("got ops:"+str(ops))
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
                        self._remove(self.saved_buffer,p,s)
                        self._remove(self.buffer,p,s)

                    # add characters and newlines
                    if 'i' in op:
                        p = op['p']
                        s = op['i']
                        self._insert(self.saved_buffer,p,s)
                        self._insert(self.buffer,p,s)
            finally:
                self.buffer_mutex.release()
        self.nvim.async_call(applyOps, self, ops)

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



