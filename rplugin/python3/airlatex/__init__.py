import pynvim
import sys
from airlatex.sidebar import SideBar
from airlatex.session import AirLatexSession
from airlatex.documentbuffer import DocumentBuffer
from airlatex.util import logging_settings


@pynvim.plugin
class AirLatex:
    def __init__(self, nvim):

        self.nvim = nvim
        self.servername = self.nvim.eval("v:servername")
        self.sidebar = False
        self.session = False

    @pynvim.command('AirLatex', nargs=0, sync=True)
    def openSidebar(self):
        # update user settings for logging
        logging_settings["level"]=self.nvim.eval("g:AirLatexLogLevel")
        logging_settings["file"]=self.nvim.eval("g:AirLatexLogFile")

        # initialize sidebar
        if not self.sidebar:
            self.sidebar = SideBar(self.nvim, self)
            self.sidebar.initGUI()
        else:
            self.sidebar.initGUI()

        # ensure session to exist
        if not self.session:
            DOMAIN = self.nvim.eval("g:airlatex_domain")
            try:
                self.session = AirLatexSession(DOMAIN, self.servername, self.sidebar, self.nvim)
                self.nvim.loop.create_task(self.session.login())
            except Exception as e:
                self.sidebar.log.error(str(e))
                self.nvim.out_write(str(e)+"\n")

    @pynvim.function('AirLatex_SidebarRefresh', sync=False)
    def sidebarRefresh(self, args):
        self.nvim.loop.create_task(self.sidebar.triggerRefresh())

    @pynvim.function('AirLatex_SidebarUpdateStatus', sync=False)
    def sidebarStatus(self, args):
        self.nvim.loop.create_task(self.sidebar.updateStatus())
        # self.sidebar.updateStatus()

    @pynvim.function('AirLatex_ProjectEnter', sync=True)
    def projectEnter(self, args):
        self.sidebar.cursorAction()

    @pynvim.function('AirLatex_ProjectLeave', sync=True)
    def projectLeave(self, args):
        self.sidebar.cursorAction("del")

    # @pynvim.command('AirLatex_UpdatePos', nargs=0, sync=True)
    # def projectEnter(self):
    #     plugin.updateProject()

    @pynvim.function('AirLatex_Close', sync=True)
    def sidebarClose(self, args):
        self.sidebar.cleanup()
        self.sidebar = None

    @pynvim.function('AirLatex_WriteBuffer', sync=True)
    def writeBuffer(self, args):
        buffer = self.nvim.current.buffer
        if buffer in DocumentBuffer.allBuffers:
            DocumentBuffer.allBuffers[buffer].writeBuffer()


