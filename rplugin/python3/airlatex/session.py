import html
import requests
import json

from airlatex.project import AirLatexProject
from airlatex.buffers import Sidebar, Comments, Splash

from airlatex.lib.task import Task
from airlatex.lib.connection import WebPage
from airlatex.lib.uuid import generateTimeStamp
from airlatex.lib.settings import Settings

from logging import getLogger


class AirLatexSession:

  def __init__(self, nvim):
    self.log = getLogger("AirLatex")
    self.settings = Settings()

    self.httpHandler = requests.Session()
    self.httpHandler.verify = not self.settings.insecure

    self.projects = {}
    self.project_data = {}
    self.authenticated = False

    Splash(nvim)
    ## Build the buffers
    # initialize sidebar
    self.sidebar = Sidebar(nvim, self)
    self.sidebar.hide()

    self.comments = Comments(nvim)
    # Show after prevents the buffers from getting in each other's way.
    self.comments.hide()
    self.sidebar.show()

  @property
  def cookies(self):
    return "; ".join(
        f"{name}={value}"
        for name, value in self.httpHandler.cookies.get_dict().items())

  @property
  def projectList(self):
    projectList = list(self.project_data.values())
    projectList.sort(key=lambda p: p.get("lastUpdated"), reverse=True)
    return projectList

  @property
  def webSocketURL(self):
    # Generating timestamp
    timestamp = generateTimeStamp()

    # To establish a websocket connection
    # the client must query for a sec url
    channelInfo = self.httpHandler.get(
        f"{self.settings.url}/socket.io/1/?t={timestamp}")
    self.log.debug(f"Websocket channelInfo '{channelInfo.text}'")
    wsChannel = channelInfo.text[:channelInfo.text.find(":")]
    self.log.debug(f"Websocket wsChannel '{wsChannel}'")

    protocol = "wss" if self.settings.https else "ws"
    return f"{protocol}://{self.settings.domain}/socket.io/1/websocket/{wsChannel}"

  async def _checkLogin(self, force=False):
    if self.authenticated and not force:
      return True

    # copy cookies to httpHandler
    for c in self.settings.cookie.replace("cookies:", "", 1).split(";"):
      if "=" not in c:
        raise ValueError("Cookie has no value. Found: %s" % c)
      name, value = c.split("=", 1)
      self.log.debug(f"Found Cookie for domain '{name}' named '{value}'")
      self.httpHandler.cookies[name] = value

    with self.sidebar.animation("Connecting"):
      # check if cookie found by testing if projects redirects to login page
      projectPage = WebPage(
          self.httpHandler,
          f"{self.settings.url}/project",
          allow_redirects=False)
      return projectPage.ok
    return False

  async def _buildProjectList(self, force=False):
    if self.authenticated and not force:
      return self.project_data

    with self.sidebar.animation("Loading Projects"):
      projectPage = WebPage(self.httpHandler, f"{self.settings.url}/project")
      self.log.debug(f"{self.settings.url}/project")

      legacy = False
      meta = projectPage.parse("prefetchedProjectsBlob")
      # Community edition still uses ol-projects
      if projectPage.ok and meta is None:
        meta = projectPage.parse("projects")
        legacy = meta is not None

      # Something went wrong
      if not projectPage.ok or meta is None:
        self.log.debug(f"{projectPage.text}, {projectPage.page}")
        Task(
            self.sidebar.updateStatus(
                f"Offline. Please Login. Error from '{self.settings.url}'.")
        ).then(
            self.sidebar.vimCursorSet, 6, 1, vim=True)
        return {}

      data = json.loads(html.unescape(meta.content))
      user_id = projectPage.parse("user_id").content
      Task(self.sidebar.updateStatus("Online"))

      self.log.debug(f"is legacy: {legacy}")
      if legacy:
        projects = {"projects": data}
        for project in data:
          owner = project["owner"]
          last_updated_by = project["lastUpdatedBy"]
          owner["firstName"] = owner.get("first_name", "")
          owner["lastName"] = owner.get("last_name", "")
          last_updated_by["firstName"] = last_updated_by.get("first_name", "")
          last_updated_by["lastName"] = last_updated_by.get("last_name", "")

    return {p["id"]: p for p in data["projects"]}

  async def start(self, msg="Disconnected"):
    self.authenticated = await self._checkLogin()
    self.project_data = await self._buildProjectList(force=True)
    Task(self.sidebar.triggerRefresh())

  async def cleanup(self, msg="Disconnected"):
    """Disconnects all connected AirLatexProjects."""
    for project in self.projects.values():
      Task(project.disconnect())
    Task(self.sidebar.updateStatus(msg))

  async def connectProject(self, project):
    """Initializing connection to a project."""
    if not self.authenticated:
      Task(self.sidebar.updateStatus("Not Authenticated to connect"))
      return None

    with self.sidebar.animation("Connecting to Projects"):
      projectPage = WebPage(
          self.httpHandler, f"{self.settings.url}/project/{project['id']}")
      csrf = projectPage.parse("csrfToken").content

      # Explicitly put it in project, as we may have injected a project
      # (e.g. on reconnect)
      project_id = project['id']
      data = self.project_data[project_id]
      data.update(project)

      socket = self.webSocketURL
      # If it exists, just trigger refresh, otherwise create a project.
      if self.projects.get(project_id):
        self.projects[project_id].refresh(
            socket, self.project_data[project_id], csrf, cookie=self.cookies)
      else:
        self.projects[project_id] = AirLatexProject(
            socket,
            data,
            csrf,
            self,
            cookie=self.cookies,
            wait_for=self.settings.wait_for,
            validate_cert=self.httpHandler.verify)
      Task(self.sidebar.updateStatus("Connected"))
    # start connection
    Task(self.projects[project_id].start())
    return self.projects[project_id]
