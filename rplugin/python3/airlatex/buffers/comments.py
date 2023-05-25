from time import gmtime, strftime

from airlatex.buffers.menu import PassiveMenuBuffer

from airlatex.lib.exceptions import pynvimCatchException
from airlatex.lib.uuid import generateCommentId
from airlatex.lib.task import Task, AsyncDecorator


class Comments(PassiveMenuBuffer):

  def __init__(self, nvim):
    super().__init__(
        nvim, actions={"Actions": {
            "Resolve": [],
            "Unresolve": []
        }})
    self.log.debug("Threads / Comments initialized.")

    self.project = None
    self.threads = {}
    self.index = 0

    self.creation = ""
    self.drafting = False

    self.comment_id = 1
    self.invalid = False

  # ------- #
  #   Api   #
  # ------- #

  @pynvimCatchException
  def buildBuffer(self):

    self.command(
        """
        let splitLocation = g:AirLatexWinPos ==# "left" ? "botright " : "topleft "
        let splitSize = g:AirLatexWinSize
        silent! exec splitLocation . 'vertical ' . splitSize . ' new'
        silent! exec "buffer " . "AirLatexComments"
        """)

    buffer = self.nvim.current.buffer

    self.command(
        """
        file AirLatexComments
        setlocal winfixwidth
        syntax clear
        setlocal noswapfile
        setlocal buftype=nofile
        setlocal bufhidden=hide
        setlocal wrap
        setlocal foldcolumn=0
        setlocal foldmethod=manual
        setlocal nofoldenable
        setlocal nobuflisted
        setlocal nospell
        setlocal nonu
        setlocal nornu
        iabc <buffer>
        setlocal cursorline
        setlocal filetype=airlatexcomment
    """)

    self.command(
        """
        nnoremap <buffer> <C-n> :call AirLatex_NextComment()<enter>
        nnoremap <buffer> <C-p> :call AirLatex_PrevComment()<enter>
        nnoremap <buffer> <enter> :call AirLatex_CommentEnter()<enter>
        au InsertEnter <buffer> :call AirLatex_DraftResponse()
        nnoremap <buffer> ZZ :call AirLatex_FinishDraft(1)<enter>
        nnoremap <buffer> ZQ :call AirLatex_FinishDraft(0)<enter>
    """)
    return buffer

  @pynvimCatchException
  def render(self, project, threads):
    if self.lock.locked():
      return

    self.project = project

    # Sort overlapping threads by time
    def lookup(thread):
      thread = project.comments.get(thread)
      if not thread:
        return -1
      for m in thread.get("messages", []):
        return m.get("timestamp", 0)
      return -1

    self.threads = sorted([t.data for t in threads], key=lookup)
    self.index = 0
    Task(self.triggerRefresh())

  @AsyncDecorator
  @pynvimCatchException
  def _render(self):
    self.log.debug(f"in render {self.threads, self.index}")
    # self.buffer[:] = []

    if self.invalid:
      self.buffer[0] = "Unable to communicate with comments server."
      self.lock.release()
      return

    if not self.threads:
      self.lock.release()
      return
    # Reset
    self.drafting = False
    self.creation = ""

    thread = self.project.comments.get(self.threads[self.index])
    if not thread:
      self.log.debug(f"all {self.threads}")
      self.lock.release()
      return

    # Eval on the fly, because it's fair this could change.
    size = self.nvim.eval("g:AirLatexWinSize")

    indicator = ""
    if len(self.threads) > 1:
      indicator = f" ({self.index + 1} / {len(self.threads)})"

    # Display Header
    menu = self.menu.clear(title=f"Comments{indicator}", size=size)

    if thread.get("resolved", False):
      menu.add_entry(f"!! Resolved")
    menu.space(1)

    for message in thread["messages"]:
      self.log.debug(f"{message['user']}")
      user = message['user'].get('first_name', '')
      if not user:
        user = message['user'].get('email', 'user')
      content = message['content']
      timestamp = message['timestamp']
      # Convert timestamp to a short date format
      short_date = strftime("%m/%d/%y %H:%M", gmtime(timestamp / 1000))

      # block is pretty heavily coupled with comment, but that's ok.
      menu.add_block(headers=[user, short_date], content=content)

    if thread.get("resolved", False):
      menu.add_entry(
          f" » reopen{' ' * (size - 4 - 7)}⬃⬃", menu.Item.Actions.Unresolve())
    else:
      menu.add_entry(
          f" » resolve{' ' * (size - 5 - 7)}✓✓", menu.Item.Actions.Resolve())

    self.write()
    if self.lock.locked():
      self.lock.release()
    self.log.debug(f"Finished Render")

  @pynvimCatchException
  def registerCursorActions(self, MenuItem, handle):

    @handle(MenuItem.Actions.Resolve)
    def resolve():
      self.project.resolveComment(self.threads[self.index])

    @handle(MenuItem.Actions.Unresolve)
    def unresolve():
      self.project.reopenComment(self.threads[self.index])

  # -------- #
  #   Misc   #
  # -------- #

  @property
  def content(self):
    content = ""
    for line in self.buffer:
      if line.startswith("#"):
        continue
      content += line + "\n"
    return content

  def hideHook(self):
    self.threads = {}
    self.index = 0
    self.creation = ""
    self.drafting = False
    self.buffer[:] = []

  async def markInvalid(self):
    self.log.debug("invalid")
    self.invalid = True
    await self.triggerRefresh()

  # ------- #
  # Actions #
  # ------- #

  @pynvimCatchException
  def finishDraft(self, submit):
    if self.invalid:
      return Task(self.triggerRefresh())

    # If on the other page
    if not self.drafting:
      self.hide()
      return Task(self.triggerRefresh())

    # Something is being written
    self.drafting = False
    # Comment reply
    if not self.creation:
      if not submit:
        return Task(self.triggerRefresh())
      self.project.replyComment(self.threads[self.index], self.content)
      return Task(self.triggerRefresh())

    # Comment submission change
    doc = self.creation
    self.creation = ""
    # Qutting, not submitting
    if not submit:
      self.menu.clear("", 0)
      # If the comment buffer wasn't set to being open,
      # return to that state.
      if self.previous_open:
        self.buffer[:] = []
      else:
        self.hide()
      return Task(self.triggerRefresh())
    # Submitting not quitting
    thread = generateCommentId(self.comment_id)
    self.comment_id += 1
    self.project.createComment(thread, doc, self.content)
    # Set pointer to current thread for refresh
    self.threads = [thread]
    self.index = 0
    return Task(self.triggerRefresh())

  @pynvimCatchException
  def prepCommentCreation(self):
    if self.invalid:
      return
    self.previous_open = self.visible
    # Swap to the window
    if self.visible:
      window = self.nvim.call('bufwinnr', self.buffer.number)
      self.command(f"exec '{window} wincmd w'")
    else:
      self.show(change=True)
    self.index = 0
    self.threads = {}
    self.nvim.feedkeys('i')

  @pynvimCatchException
  def prepCommentRespond(self):
    self.menu.clear("", 0)
    if self.invalid:
      return
    if not self.drafting:
      p = lambda S: [s.strip() for s in S.split("\n")]
      self.buffer[:] = p(
          """
      #
      # Drafting comment.
      # Lines starting with '#' will be ignored.
      # Do ZZ to save and send.
      # Do ZQ to quit without sending.
      #""")
      self.drafting = True

  @pynvimCatchException
  def changeComment(self, change):
    if self.invalid:
      return
    self.index = (self.index + change) % len(self.threads)
    Task(self.triggerRefresh())
