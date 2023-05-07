import traceback
import keyring
import pynvim
import platform
from sys import version_info
from asyncio import create_task
from airlatex.sidebar import SideBar
from airlatex.session import AirLatexSession
from airlatex.commentbuffer import CommentBuffer
from airlatex.documentbuffer import DocumentBuffer
from airlatex.util import logging_settings, init_logger, __version__


@pynvim.plugin
class AirLatex:
    def __init__(self, nvim):

        self.nvim = nvim
        self.servername = self.nvim.eval("v:servername")
        self.sidebar = False
        self.comments = False
        self.session = False
        self.nvim.command("let g:AirLatexIsActive = 1")

    def __del__(self):
        self.nvim.command("let g:AirLatexIsActive = 0")

    @pynvim.command('AirLatex', nargs=0, sync=True)
    def openSidebar(self):

        # update user settings for logging
        logging_settings["level"]=self.nvim.eval("g:AirLatexLogLevel")
        logging_settings["file"]=self.nvim.eval("g:AirLatexLogFile")
        log = init_logger()
        log.info("Starting AirLatex (Version %s)" % __version__)
        log.info("System Info:")
        log.info("  - Python Version: %i.%i" % (version_info.major, version_info.minor))
        log.info("  - OS: %s (%s)" % (platform.system(), platform.release()))
        self.log = log

        # initialize exception handling for asyncio
        self.nvim.loop.set_exception_handler(self.asyncCatchException)

        # initialize sidebar
        if not self.sidebar:
            self.sidebar = SideBar(self.nvim, self)
        self.sidebar.initGUI()
        self.sidebar.hide()

        # initialize comment buffer
        if not self.comments:
            self.comments = CommentBuffer(self.nvim, self)
        self.comments.initGUI()

        self.sidebar.show()

        # ensure session to exist
        if not self.session:
            DOMAIN = self.nvim.eval("g:AirLatexDomain")
            https = self.nvim.eval("g:AirLatexUseHTTPS")
            username = self.nvim.eval("g:AirLatexUsername")

            # query credentials
            if username.startswith("cookies"):
                if not username[7:]:
                    self.nvim.command("call inputsave()")
                    self.nvim.command("let user_input = input(\"Cookie given '%s'.\nLogin in your browser & paste it here: \")" % (DOMAIN))
                    self.nvim.command("call inputrestore()")
                    self.nvim.command("let g:AirLatexUsername='cookies:%s'" % self.nvim.eval("user_input"))
            else:
                password = keyring.get_password("airlatex_"+DOMAIN, username)
                while password is None:
                    self.nvim.command("call inputsave()")
                    self.nvim.command("let user_input = input(\"No Password found for '%s' and user '%s'.\nType it in to store it in keyring: \")" % (DOMAIN, username))
                    self.nvim.command("call inputrestore()")
                    keyring.set_password("airlatex_"+DOMAIN, username, self.nvim.eval("user_input"))
                    password = keyring.get_password("airlatex_"+DOMAIN, username)
            # connect
            try:
                self.session = AirLatexSession(DOMAIN, self.servername, self.sidebar, self.nvim, https=https)
                create_task(self.session.login())
            except Exception as e:
                self.sidebar.log.error(str(e))
                self.nvim.out_write(str(e)+"\n")

    @pynvim.command('AirLatexResetPassword', nargs=0, sync=True)
    def resetPassword(self):
        DOMAIN = self.nvim.eval("g:AirLatexDomain")
        username = self.nvim.eval("g:AirLatexUsername")
        keyring.delete_password("airlatex_"+DOMAIN, username)
        self.nvim.command("call inputsave()")
        self.nvim.command("let user_input = input(\"Resetting password for '%s' and user '%s'.\nType it in to store it in keyring: \")" % (DOMAIN, username))
        self.nvim.command("call inputrestore()")
        keyring.set_password("airlatex_"+DOMAIN, username, self.nvim.eval("user_input"))

    @pynvim.function('AirLatex_SidebarRefresh', sync=False)
    def sidebarRefresh(self, args):
        if self.sidebar:
            create_task(self.sidebar.triggerRefresh())

    @pynvim.function('AirLatex_SidebarUpdateStatus', sync=False)
    def sidebarStatus(self, args):
        create_task(self.sidebar.updateStatus())

    @pynvim.function('AirLatex_ProjectEnter', sync=True)
    def projectEnter(self, args):
        if self.sidebar:
            self.sidebar.cursorAction()

    @pynvim.function('AirLatex_ProjectLeave', sync=True)
    def projectLeave(self, args):
        if self.sidebar:
            self.sidebar.cursorAction("del")

    # @pynvim.command('AirLatex_UpdatePos', nargs=0, sync=True)
    # def projectEnter(self):
    #     plugin.updateProject()

    @pynvim.function('AirLatex_Compile', sync=True)
    def compile(self, args):
        buffer = self.nvim.current.buffer
        if buffer in DocumentBuffer.allBuffers:
            DocumentBuffer.allBuffers[buffer].compile()

    @pynvim.function('AirLatexToggle', sync=True)
    def toggle(self, args):
        self.sidebar.toggle()

    @pynvim.function('AirLatexToggleComments', sync=True)
    def toggleComments(self, args):
        self.comments.toggle()

    @pynvim.function('AirLatexToggleTracking', sync=True)
    def toggleTracking(self, args):
        # Should be set, but just in case
        tracking = self.nvim.eval("g:AirLatexTrackChanges")
        self.nvim.command(f"let g:AirLatexTrackChanges={1 - tracking}")

    @pynvim.function('AirLatex_Close', sync=True)
    def sidebarClose(self, args):
        if self.sidebar:
            self.session.cleanup()
            self.sidebar = None

    @pynvim.function('AirLatex_WriteBuffer', sync=True)
    def writeBuffer(self, args):
        buffer = self.nvim.current.buffer
        if buffer in DocumentBuffer.allBuffers:
            DocumentBuffer.allBuffers[buffer].writeBuffer()

    @pynvim.function('AirLatex_ShowComments')
    def showComments(self, args):
        buffer = self.nvim.current.buffer
        if buffer in DocumentBuffer.allBuffers:
            DocumentBuffer.allBuffers[buffer].showComments(self.comments)

    @pynvim.function('AirLatex_NextComment')
    def nextComment(self, args):
        self.comments.changeComment(1)

    @pynvim.function('AirLatex_PrevComment')
    def prevComment(self, args):
        self.comments.changeComment(-1)

    def asyncCatchException(self, loop, context):
        message = context.get('message')
        if not message:
            message = 'Unhandled exception in event loop'

        exception = context.get('exception')
        if exception is not None:
            exc_info = (type(exception), exception, exception.__traceback__)
        else:
            exc_info = False

        self.log.error(message, exc_info=exc_info)
        self.log.info("Shutting down...")
        loop.create_task(self.session.cleanup("Error: '%s'." % message))
