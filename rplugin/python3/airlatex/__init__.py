import pynvim

from airlatex.lib.task import Task, AsyncDecorator
from airlatex.lib.log import init_logger
from airlatex.lib.settings import Settings

from airlatex.session import AirLatexSession
from airlatex.buffers import Document


@pynvim.plugin
class AirLatex():

  def __init__(self, nvim):

    self.nvim = nvim
    AsyncDecorator.nvim = nvim

    self.session = None
    self.started = False

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
    if self.started:
      return
    self.started = True

    # Attempt connection and start
    self.session = AirLatexSession(self.nvim)
    try:
      Task(self.session.start)
    except Exception as e:
      self.session.sidebar.log.error(str(e))
      self.nvim.out_write(str(e) + "\n")

  @pynvim.function('AirLatex_SidebarRefresh', sync=False)
  def sidebarRefresh(self, args):
    if self.session.sidebar:
      Task(self.session.sidebar.triggerRefresh())

  @pynvim.function('AirLatex_SidebarUpdateStatus', sync=False)
  def sidebarStatus(self, args):
    Task(self.session.sidebar.updateStatus())

  @pynvim.function('AirLatex_ProjectEnter', sync=True)
  def projectEnter(self, args):
    if self.session.sidebar:
      self.session.sidebar.cursorAction()

  @pynvim.function('AirLatex_CommentEnter', sync=True)
  def commentEnter(self, args):
    if self.session.comments:
      self.session.comments.cursorAction()

  @pynvim.function('AirLatex_CommentSelection', sync=True)
  def commentSelection(self, args):
    if (self.session.comments.creation or self.session.comments.drafting or self.session.comments.invalid):
      return
    start_line, start_col = self.nvim.call('getpos', "'<")[1:3]
    end_line, end_col = self.nvim.call('getpos', "'>")[1:3]
    end_col += 1
    # Visual line selection sets end_col to max int
    # So just set to the next line.
    if end_col == 2147483648:
      end_col = 1
      end_line += 1

    buffer = self.nvim.current.buffer
    if buffer in Document.allBuffers:
      document = Document.allBuffers[buffer]
      self.session.comments.creation = document.id
      self.session.comments.project = document.project
      document.markComment(
          start_line - 1, start_col - 1, end_line - 1, end_col - 1)
      self.session.comments.prepCommentCreation()

  @pynvim.function('AirLatex_DraftResponse', sync=True)
  def commentDraft(self, args):
    if self.session.comments:
      self.session.comments.prepCommentRespond()

  @pynvim.function('AirLatex_FinishDraft', sync=True)
  def commentRespond(self, args):
    if self.session.comments:
      self.session.comments.finishDraft(*args)

  @pynvim.function('AirLatex_ProjectLeave', sync=True)
  def projectLeave(self, args):
    if self.session.sidebar:
      self.session.sidebar.cursorAction("del")

  @pynvim.function('AirLatex_Compile', sync=True)
  def compile(self, args):
    buffer = self.nvim.current.buffer
    if buffer in Document.allBuffers:
      Task(Document.allBuffers[buffer].project.compile())

  @pynvim.function('AirLatex_GitSync', sync=True)
  def syncGit(self, args):
    buffer = self.nvim.current.buffer
    if buffer in Document.allBuffers:
      message, = args
      while not message:
        message = self.nvim.funcs.input('Commit Message: ')
      @Task.Fn()
      async def _trySync():
        status, msg = await Document.allBuffers[buffer].project.syncGit(message)
        Task(self.nvim.command, f"echo '{msg}'", vim=True)

  @pynvim.function('AirLatexToggle', sync=True)
  def toggle(self, args):
    self.session.sidebar.toggle()

  @pynvim.function('AirLatexToggleComments', sync=True)
  def toggleComments(self, args):
    self.session.comments.toggle()

  @pynvim.function('AirLatexToggleTracking', sync=True)
  def toggleTracking(self, args):
    # Should be set, but just in case
    tracking = self.nvim.eval("g:AirLatexTrackChanges")
    self.nvim.command(f"let g:AirLatexTrackChanges={1 - tracking}")

  @pynvim.function('AirLatex_Close', sync=True)
  def sidebarClose(self, args):
    if self.session.sidebar:
      self.session.cleanup()

  @pynvim.function('AirLatex_WriteBuffer', sync=True)
  def writeBuffer(self, args):
    buffer = self.nvim.current.buffer
    if buffer in Document.allBuffers:
      Document.allBuffers[buffer].writeBuffer()

  @pynvim.function('AirLatex_MoveCursor', sync=True)
  def moveCursor(self, args):
    buffer = self.nvim.current.buffer
    if buffer in Document.allBuffers:
      Document.allBuffers[buffer].writeBuffer(self.session.comments)

  @pynvim.function('AirLatex_ChangeCommentPosition')
  def changeCommentPosition(self, args):
    kwargs = {"prev": args[-1] < 0, "next": args[-1] > 0}
    buffer = self.nvim.current.buffer
    if buffer in Document.allBuffers:
      buffer = Document.allBuffers[buffer]
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
    self.session.comments.changeComment(1)

  @pynvim.function('AirLatex_PrevComment')
  def prevComment(self, args):
    self.session.comments.changeComment(-1)

  @pynvim.function('AirLatex_Refresh')
  def refresh(self, args):
    pid, did = args
    cursor = self.nvim.current.window.cursor[:]

    # TODO move out of init.
    # Probs to session and Document
    async def get_joined_doc(project):
      await project.join_event.wait()
      def recurse(root, path):
        self.log.debug(f"{root}")
        for doc in root["docs"]:
          if did == doc["_id"]:
            self.log.debug(f"Returning data {doc, project}")
            return path + [doc], doc, project
        for f in root["folders"]:
          return recurse(f, path + [f])
      for root in project.data["rootFolder"]:
        data = recurse(root, [root])
        if data:
          break

      if not data:
        raise Exception(f"Doc not found")
      return data

    # Rejoin vim thread
    @AsyncDecorator
    def build_buffer(path, doc, project):
      self.log.debug(f"{path}")
      document = Document(self.nvim, project, path, doc, new_buffer=False)
      Task(project.joinDocument(document))
      return document.buffer_event.wait

    @AsyncDecorator
    def set_cursor():
      row = min(cursor[0], len(self.nvim.current.buffer) - 1)
      column = min(cursor[1], len(self.nvim.current.buffer[row]) - 1)
      self.nvim.current.window.cursor = [row, column]

    # If the project is already connected, then just use the exisiting
    # connection to reconnect
    if self.session.project_data.get(pid, {}).get("connected", False):
      task = Task(get_joined_doc, self.session.projects[pid])
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
    if self.session:
      loop.create_task(self.session.cleanup("Error: '%s'." % message))
