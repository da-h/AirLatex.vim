import html
import pynvim
import keyring
import requests
import json
import time
import tempfile
from threading import Thread, currentThread
from asyncio import Lock, sleep
from queue import Queue
from os.path import expanduser
import re
from airlatex.project_handler import AirLatexProject
from airlatex.util import _genTimeStamp
from http.cookiejar import CookieJar
from logging import getLogger
import traceback

from airlatex.task import AsyncDecorator, Task

class AirLatexSession:

  def __init__(self, domain, servername, sidebar, comments, nvim, https=True):
    """
      Manages the Session to the server:
      - tries to login with credentials & checks wether these suffice as authentication
      - queries the project list
      - initializes AirLatexProject objects
    """

    self.sidebar = sidebar
    self.comments = comments
    self.nvim = nvim
    self.servername = servername
    self.domain = domain
    self.https = True if https else False
    self.url = ("https://" if https else "http://") + domain
    self.authenticated = False
    self.httpHandler = requests.Session()
    self.httpHandler.verify = False if self.nvim.eval(
        "g:AirLatexAllowInsecure") == 1 else True
    self.projects = {}
    self.log = getLogger("AirLatex")

    self.wait_for = self.nvim.eval("g:AirLatexWebsocketTimeout")
    self.username = self.nvim.eval("g:AirLatexUsername")

  # ------- #
  # helpers #
  # ------- #

  @property
  def cookies(self):
    return "; ".join(
        f"{name}={value}"
        for name, value in self.httpHandler.cookies.get_dict().items())

  @property
  def projectList(self):
    projectList = list(self.projects.values())
    projectList.sort(key=lambda p: p.get("lastUpdated"), reverse=True)
    return projectList

  async def _getWebSocketURL(self):
    """
        Query websites websocket meta information to be used for further connections.
        """
    if self.authenticated:
      # Generating timestamp
      timestamp = _genTimeStamp()

      # To establish a websocket connection
      # the client must query for a sec url
      self.httpHandler.get(self.url + "/project")
      channelInfo = self.httpHandler.get(
          self.url + "/socket.io/1/?t=" + timestamp)
      self.log.debug("Websocket channelInfo '%s'" % channelInfo.text)
      wsChannel = channelInfo.text[0:channelInfo.text.find(":")]
      self.log.debug("Websocket wsChannel '%s'" % wsChannel)
      return (
          "wss://" if self.https else
          "ws://") + self.domain + "/socket.io/1/websocket/" + wsChannel

  # --- #
  # api # (to be used by pynvim.plugin)
  # --- #

  async def cleanup(self, msg="Disconnected"):
    """
        Disconnects all connected AirLatexProjects.
        """
    self.log.debug("cleanup()")
    for p in self.projects.values():
      if "handler" in p:
        p["handler"].disconnect()
      p["connected"] = False
    Task(self.sidebar.updateStatus(msg))

  async def login(self):
    """
        Test authentication by opening webpage & retrieving project list.
        """
    self.log.debug("login()")
    if not self.authenticated:

      if not self.username.startswith("cookies:"):

        anim_status = Task(self.sidebar.animate("Login"))

        # get csrf token
        loginpage_request = lambda: self.httpHandler.get(self.url + "/login")
        loginpage = await self.nvim.loop.run_in_executor(
            None, loginpage_request)
        if loginpage.ok:
          csrf_input = re.search(
              '<input\s[^>]*name="_csrf"[^>]*>', loginpage.text)
          csrf = re.search('value="([^"]*)"',
                           csrf_input[0])[1] if csrf_input else None

        # try to login
        try:
          data = {
              "email":
                  self.username,
              "password":
                  keyring.get_password(
                      "airlatex_" + self.domain, self.username)
          }
          if csrf is not None:
            data["_csrf"] = csrf
          login = lambda: self.httpHandler.post(self.url + "/login", data=data)
          login_response = await self.nvim.loop.run_in_executor(None, login)
          anim_status.cancel()
          if not login_response.ok:
            with tempfile.NamedTemporaryFile(delete=False) as f:
              f.write(login_response.text.encode())
              Task(
                  self.sidebar.updateStatus(
                      f"Could not login using the credentials. You can check"
                      " the response page under: {f.name}"))
              return False
        except Exception as e:
          anim_status.cancel()
          self.log.debug(traceback.format_exc())
          Task(self.sidebar.updateStatus("Login failed: " + str(e)))
          return False

      else:
        # copy cookies to httpHandler
        for c in self.username[8:].split(";"):
          if "=" not in c:
            raise ValueError("Cookie has no value. Found: %s" % c)
          name, value = c.split("=", 1)
          self.log.debug(
              "Found Cookie for domain '%s' named '%s'" % (name, value))
          self.httpHandler.cookies[name] = value

      anim_status = Task(self.sidebar.animate("Connecting"))
      # check if cookie found by testing if projects redirects to login page
      try:
        get = lambda: self.httpHandler.get(
            self.url + "/project", allow_redirects=False)
        redirect = await self.nvim.loop.run_in_executor(None, get)
        anim_status.cancel()
        if redirect.ok:

          self.authenticated = True
          await self.updateProjectList()
          return True
        else:
          self.log.debug(
              "Could not fetch '%s/project'. Response chain: %s" %
              (self.url, str(redirect)))
          with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(redirect.text.encode())
            Task(
                self.sidebar.updateStatus(
                    "Connection failed: I could not retrieve the project list."
                    " You can check the response page under: {f.name}"))
          return False
      except Exception as e:
        anim_status.cancel()
        self.log.debug(traceback.format_exc())
        Task(self.sidebar.updateStatus("Connection failed: " + str(e)))
    else:
      return False

  async def updateProjectList(self):
    """
        Retrieves project list.
        """
    self.log.debug("updateProjectList()")
    if self.authenticated:
      anim_status = Task(self.sidebar.animate("Loading Projects"))

      get = lambda: self.httpHandler.get(
          self.url + "/project", allow_redirects=False)
      projectPage = (await self.nvim.loop.run_in_executor(None, get))
      anim_status.cancel()

      legacy = False
      meta = re.search(
          '<meta\s[^>]*name="ol-prefetchedProjectsBlob"[^>]*>',
          projectPage.text) if projectPage.ok else None
      # Community edition still uses ol-projects
      if projectPage.ok and meta is None:
        meta = re.search(
            '<meta\s[^>]*name="ol-projects"[^>]*>',
            projectPage.text) if projectPage.ok else None
        legacy = meta is not None

      if not projectPage.ok or meta is None:
        with tempfile.NamedTemporaryFile(delete=False) as f:
          f.write(projectPage.text.encode())
          self.authenticated = False
          Task(self.sidebar.updateStatus(
                  f"Offline. Please Login. I saved the webpage '{self.url}' I"
                  " got under {f.name}.")).then(self.sidebar.vimCursorSet, 6, 1,
                                               vim=True)
          Task(self.sidebar.triggerRefresh())
        return []

      try:
        project_data_escaped = re.search('content="([^"]*)"', meta[0])[1]
        data = html.unescape(project_data_escaped)
        self.log.debug("project_data=" + data)
        data = json.loads(data)
        self.user_id = re.search(
            'content="([^"]*)"',
            re.search('<meta\s[^>]*name="ol-user_id"[^>]*>',
                      projectPage.text)[0])[1]
        Task(self.sidebar.updateStatus("Online"))
        self.log.debug(data)

        if legacy:
          self.log.debug("is legacy")
          projects = data
          for project in projects:
            owner = project["owner"]
            last_updated_by = project["lastUpdatedBy"]
            owner["firstName"] = owner.get("first_name", "")
            owner["lastName"] = owner.get("last_name", "")
            last_updated_by["firstName"] = last_updated_by.get("first_name", "")
            last_updated_by["lastName"] = last_updated_by.get("last_name", "")
        else:
          self.log.debug("is NOT legacy")
          projects = data["projects"]
        self.projects = {p["id"]: p for p in projects}
        Task(self.sidebar.triggerRefresh())
      except Exception as e:

        with tempfile.NamedTemporaryFile(delete=False) as f:
          f.write(projectPage.text.encode())
          Task(
              self.sidebar.updateStatus(
                  "Could not retrieve project list: %s. You can check the response page under: %s "
                  % (str(e), f.name)))
        self.log.debug(traceback.format_exc())
        Task(self.sidebar.triggerRefresh())

  async def connectProject(self, project):
    """
        Initializing connection to a project.
        """
    if not self.authenticated:
      Task(self.sidebar.updateStatus("Not Authenticated to connect"))
      return None

    anim_status = Task(
        self.sidebar.animate("Connecting to Project"))

    get = lambda: self.httpHandler.get(
        f"{self.url}/project/{project['id']}", allow_redirects=False)
    projectPage = (await self.nvim.loop.run_in_executor(None, get))
    csrf = re.search(
        'content="([^"]*)"',
        re.search('<meta\s[^>]*name="ol-csrfToken"[^>]*>',
                  projectPage.text)[0])[1]

    # Explicitly put it in proect, as we may have injected a project
    # (e.g. on reconnect)
    self.projects[project['id']].update(project)
    if self.projects[project['id']].get("handler"):
      airlatexproject = self.projects[project['id']]["handler"]
      airlatexproject.refresh(
          await self._getWebSocketURL(),
          self.projects[project['id']],
          csrf,
          cookie=self.cookies)
    else:
      # Side bar set command in document
      airlatexproject = AirLatexProject(
          await self._getWebSocketURL(),
          self.projects[project['id']],
          csrf,
          self,
          cookie=self.cookies,
          wait_for=self.wait_for,
          validate_cert=self.httpHandler.verify)
      self.projects[project['id']]["handler"] = airlatexproject

    # start connection
    anim_status.cancel()
    Task(self.sidebar.updateStatus("Connected"))
    Task(airlatexproject.start())
    return airlatexproject
