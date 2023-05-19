import pynvim
from airlatex.task import Task, AsyncDecorator
from airlatex.session import AirLatexSession

# from airlatex.buffers import SideBar, CommentBuffer, DocumentBuffer
from airlatex.sidebar import SideBar
# from airlatex.commentbuffer import CommentBuffer
from airlatex.documentbuffer import DocumentBuffer

from airlatex.util import init_logger, Settings


@pynvim.plugin
class AirLatex:

  def __init__(self, nvim):

    self.nvim = nvim
    AsyncDecorator.nvim = nvim

    self.sidebar = None
    self.comments = None
    self.session = None

    self.nvim.command("let g:AirLatexIsActive = 1")
    self.settings = Settings(
        wait_for=self.nvim.eval("g:AirLatexWebsocketTimeout"),
        username=self.nvim.eval("g:AirLatexUsername"),
        domain=self.nvim.eval("g:AirLatexDomain"),
        https=self.nvim.eval("g:AirLatexUseHTTPS"),
        insecure=self.nvim.eval("g:AirLatexAllowInsecure") == 1)

    # initialize exception handling for asyncio
    self.nvim.loop.set_exception_handler(self.asyncCatchException)

    # update user settings for logging
    self.log = init_logger(
        self.nvim.eval("g:AirLatexLogLevel"),
        self.nvim.eval("g:AirLatexLogFile"))

  def __del__(self):
    self.nvim.command("let g:AirLatexIsActive = 0")

  @pynvim.command('AirLatex', nargs=0, sync=True)
  def startSession(self):
    if self.session:
      return

    # initialize sidebar
    if not self.sidebar:
      self.sidebar = SideBar(self.nvim, self)
    self.sidebar.initGUI()
    # self.sidebar.hide()

    # # initialize comment buffer
    # if not self.comments:
    #   self.comments = CommentBuffer(self.nvim, self)
    # self.comments.initGUI()

    # # Show after prevents the buffers from gettin in each other's way.
    # self.sidebar.show()

    # Attempt connection and start
    try:
      self.session = AirLatexSession(self.sidebar, self.comments)
      Task(self.session.start)
    except Exception as e:
      self.sidebar.log.error(str(e))
      self.nvim.out_write(str(e) + "\n")

  @pynvim.function('AirLatex_SidebarRefresh', sync=False)
  def sidebarRefresh(self, args):
    if self.sidebar:
      Task(self.sidebar.triggerRefresh())

  @pynvim.function('AirLatex_SidebarUpdateStatus', sync=False)
  def sidebarStatus(self, args):
    Task(self.sidebar.updateStatus())

  @pynvim.function('AirLatex_ProjectEnter', sync=True)
  def projectEnter(self, args):
    if self.sidebar:
      self.sidebar.cursorAction()

  @pynvim.function('AirLatex_CommentEnter', sync=True)
  def commentEnter(self, args):
    if self.comments:
      self.comments.cursorAction()

  @pynvim.function('AirLatex_CommentSelection', sync=True)
  def commentSelection(self, args):
    if self.comments.creation or self.comments.drafting:
      return
    start_line, start_col = self.nvim.call('getpos', "'<")[1:3]
    end_line, end_col = self.nvim.call('getpos', "'>")[1:3]
    end_col += 1
    # Visual line selection sets end_col to max int
    # So just set to the next line.
    if end_col == 2147483648:
      end_col = 1
      end_line += 1

    if self.comments.invalid:
      return
    buffer = self.nvim.current.buffer
    if buffer in DocumentBuffer.allBuffers:
      document = DocumentBuffer.allBuffers[buffer]
      self.comments.creation = document.document["_id"]
      self.comments.project = document.project_handler
      document.markComment(
          start_line - 1, start_col - 1, end_line - 1, end_col - 1)
      self.comments.prepCommentCreation()

  @pynvim.function('AirLatex_DraftResponse', sync=True)
  def commentDraft(self, args):
    if self.comments:
      self.comments.prepCommentRespond()

  @pynvim.function('AirLatex_FinishDraft', sync=True)
  def commentRespond(self, args):
    if self.comments:
      self.comments.finishDraft(*args)

  @pynvim.function('AirLatex_ProjectLeave', sync=True)
  def projectLeave(self, args):
    if self.sidebar:
      self.sidebar.cursorAction("del")

  @pynvim.function('AirLatex_Compile', sync=True)
  def compile(self, args):
    buffer = self.nvim.current.buffer
    if buffer in DocumentBuffer.allBuffers:
      DocumentBuffer.allBuffers[buffer].compile()

  @pynvim.function('AirLatex_GitSync', sync=True)
  def compile(self, args):
    buffer = self.nvim.current.buffer
    if buffer in DocumentBuffer.allBuffers:
      DocumentBuffer.allBuffers[buffer].syncGit(*args)

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
      self.comments = None
      self.sidebar = None

  @pynvim.function('AirLatex_WriteBuffer', sync=True)
  def writeBuffer(self, args):
    buffer = self.nvim.current.buffer
    if buffer in DocumentBuffer.allBuffers:
      DocumentBuffer.allBuffers[buffer].writeBuffer()

  @pynvim.function('AirLatex_MoveCursor', sync=True)
  def moveCursor(self, args):
    buffer = self.nvim.current.buffer
    if buffer in DocumentBuffer.allBuffers:
      DocumentBuffer.allBuffers[buffer].writeBuffer(self.comments)

  @pynvim.function('AirLatex_ChangeCommentPosition')
  def changeCommentPosition(self, args):
    kwargs = {"prev": args[-1] < 0, "next": args[-1] > 0}
    buffer = self.nvim.current.buffer
    if buffer in DocumentBuffer.allBuffers:
      buffer = DocumentBuffer.allBuffers[buffer]
      pos, offset = buffer.getCommentPosition(**kwargs)
      # Maybe print warning?
      if not offset:
        return
      self.nvim.current.window.cursor = pos
      self.nvim.command(f"let g:AirLatexCommentCount={offset}")
      self.nvim.command(
          f"echo 'Comment {offset}/{len(buffer.thread_intervals)}'")

  @pynvim.function('AirLatex_PrevCommentPosition')
  def prevCommentPosition(self, args):
    self.changeCommentPosition([-1])

  @pynvim.function('AirLatex_NextCommentPosition')
  def nextCommentPosition(self, args):
    self.changeCommentPosition([1])

  @pynvim.function('AirLatex_NextComment')
  def nextComment(self, args):
    self.comments.changeComment(1)

  @pynvim.function('AirLatex_PrevComment')
  def prevComment(self, args):
    self.comments.changeComment(-1)

  @pynvim.function('AirLatex_Refresh')
  def refresh(self, args):
    pid, did = args
    cursor = self.nvim.current.window.cursor[:]

    # TODO move out of init.
    # Probs to session and DocumentBuffer
    async def get_joined_doc(handler):
      await handler.join_event.wait()
      for folder in handler.project["rootFolder"]:
        for doc in folder["docs"]:
          if did == doc["_id"]:
            self.log.debug(f"Returning data {doc, handler}")
            return doc, handler
      if not found:
        self.log.debug(f"Doc not found..?")
        raise Exception(f"{pid, did}")

    # Rejoin vim thread
    @AsyncDecorator
    def build_buffer(doc, handler):
      self.log.debug(f"Queing tasks")
      documentbuffer = DocumentBuffer(
          [handler.project, doc], self.nvim, new_buffer=False)
      self.log.debug(f"Built docs")
      Task(handler.joinDocument(documentbuffer))
      Task(handler.gui_await())
      self.log.debug(f"Starting wait")
      return documentbuffer.buffer_event.wait

    @AsyncDecorator
    def set_cursor():
      row = min(cursor[0], len(self.nvim.current.buffer) - 1)
      column = min(cursor[1], len(self.nvim.current.buffer[row]) - 1)
      self.nvim.current.window.cursor = [row, column]

    # If the project is already connected, then just use the exisiting
    # connection to reconnect
    if self.session.projects.get(pid, {}).get("connected", False):
      task = Task(get_joined_doc, self.session.projects[pid]["handler"])
    else:
      task = Task(
          self.session.connectProject, {
              "id": pid,
              "name": "reloading"
          }).then(get_joined_doc)
    # Finish off the progression
    task.then(build_buffer).next.then(set_cursor)

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
