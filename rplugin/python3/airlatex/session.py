import pynvim
import browser_cookie3
import requests
import json
import time
import tempfile
from threading import Thread, currentThread
from asyncio import Lock, sleep, create_task
from queue import Queue
from os.path import expanduser
import re
from airlatex.project_handler import AirLatexProject
from airlatex.util import _genTimeStamp
from http.cookiejar import CookieJar
from logging import getLogger



class AirLatexSession:

    def __init__(self, domain, servername, sidebar, nvim, https=True):
        """
        Manages the Session to the server:
        - queries cookies & checks wether these suffice as authentication
        - queries the project list
        - initializes AirLatexProject objects
        """

        self.sidebar = sidebar
        self.nvim = nvim
        self.servername = servername
        self.domain = domain
        self.https = True if https else False
        self.url = ("https://" if https else "http://") + domain
        self.authenticated = False
        self.httpHandler = requests.Session()
        self.projectList = []
        self.log = getLogger("AirLatex")

        self.wait_for = self.nvim.eval("g:AirLatexWebsocketTimeout")
        self._updateCookies()


    # ------- #
    # helpers #
    # ------- #

    def _updateCookies(self):
        """
        Queries cookies using browser_cookie3 and caches them (self.cj).
        """

        # guess cookie dir (browser_cookie3 does that already mostly)
        browser   = self.nvim.eval("g:AirLatexCookieBrowser")
        if browser == "auto":
            cj = browser_cookie3.load()
        elif browser.lower() == "firefox":
            cj = browser_cookie3.firefox()
        elif browser.lower() == "chrome" or browser.lower() == "chromium":
            cj = browser_cookie3.chrome()
        else:
            raise ValueError("AirLatexCookieBrowser '%s' should be one of 'auto', 'firefox', 'chromium' or 'chrome'" % browser)

        self.cj = CookieJar()
        for c in cj:
            if c.domain in self.url or self.url in c.domain:
                self.log.debug("Found Cookie for domain '%s' named '%s'" % (c.domain, c.name))
                self.cj.set_cookie(c)

    async def _makeStatusAnimation(self, str):
        """
        Performs a loading animation.
        """
        i = 0
        while True:
            s = " .." if i%3 == 0 else ". ." if i%3 == 1 else ".. "
            await self.sidebar.updateStatus(s + " " + str + " " + s)
            await sleep(0.1)
            i += 1

    async def _getWebSocketURL(self):
        """
        Query websites websocket meta information to be used for further connections.
        """
        if self.authenticated:
            # Generating timestamp
            timestamp = _genTimeStamp()

            # To establish a websocket connection
            # the client must query for a sec url
            self.httpHandler.get(self.url + "/project", cookies=self.cj)
            channelInfo = self.httpHandler.get(self.url + "/socket.io/1/?t="+timestamp, cookies=self.cj)
            self.log.debug("Websocket channelInfo '%s'"%channelInfo.text)
            wsChannel = channelInfo.text[0:channelInfo.text.find(":")]
            self.log.debug("Websocket wsChannel '%s'"%wsChannel)
            return ("wss://" if self.https else "ws://") + self.domain + "/socket.io/1/websocket/"+wsChannel


    # --- #
    # api # (to be used by pynvim.plugin)
    # --- #

    async def cleanup(self, msg="Disconnected"):
        """
        Disconnects all connected AirLatexProjects.
        """
        self.log.debug("cleanup()")
        for p in self.projectList:
            if "handler" in p:
                p["handler"].disconnect()
            p["connected"] = False
        create_task(self.sidebar.updateStatus(msg))

    async def login(self):
        """
        Test authentication by opening webpage & retrieving project list.
        """
        self.log.debug("login()")
        if not self.authenticated:
            anim_status = create_task(self._makeStatusAnimation("Connecting"))

            # check if cookie found by testing if projects redirects to login page
            try:
                get = lambda: self.httpHandler.get(self.url + "/project", cookies=self.cj)
                redirect = await self.nvim.loop.run_in_executor(None, get)
                anim_status.cancel()
                if redirect.ok:

                    # overwrite cookies in case there has been an update
                    for name, value in self.httpHandler.cookies.get_dict().items():
                        cookie = requests.cookies.create_cookie(name, value)
                        self.cj.set_cookie(cookie)

                    self.authenticated = True
                    await self.updateProjectList()
                    return True
                else:
                    self.log.debug("Could not fetch '%s/project'. Response chain: %s" % (self.url, str(redirect)))
                    with tempfile.NamedTemporaryFile(delete=False) as f:
                        f.write(redirect.text.encode())
                        create_task(self.sidebar.updateStatus("Connection failed: I could not retrieve the project list. You can check the response page under: %s" % f.name))
                    return False
            except Exception as e:
                create_task(self.sidebar.updateStatus("Connection failed: "+str(e)))
        else:
            return False

    async def updateProjectList(self):
        """
        Retrieves project list.
        """
        self.log.debug("updateProjectList()")
        if self.authenticated:
            anim_status = create_task(self._makeStatusAnimation("Loading Projects"))

            get = lambda: self.httpHandler.get(self.url + "/project", cookies=self.cj)
            projectPage = (await self.nvim.loop.run_in_executor(None, get)).text
            pos_script_1  = projectPage.find("<script id=\"data\"")
            pos_script_2 = projectPage.find(">", pos_script_1 + 20)
            pos_script_close = projectPage.find("</script", pos_script_2 + 1)
            anim_status.cancel()

            if pos_script_1 == -1 or pos_script_2 == -1 or pos_script_close == -1:
                with tempfile.NamedTemporaryFile(delete=False) as f:
                    f.write(projectPage.encode())
                    self.authenticated = False
                    create_task(self.sidebar.updateStatus("Offline. Please Login. I saved the webpage '%s' I got under %s. Cookies that has been used to authenticate are %s" % (self.url, f.name, ",".join([c.name for c in self.cj]))))
                    self.nvim.async_call(self.sidebar.vimCursorSet, 6, 1)
                    create_task(self.sidebar.triggerRefresh())
                return []
            data = projectPage[pos_script_2+1:pos_script_close]
            data = json.loads(data)
            self.user_id = re.search("user_id\s*:\s*'([^']+)'",projectPage)[1]
            create_task(self.sidebar.updateStatus("Online"))

            self.projectList = data["projects"]
            self.projectList.sort(key=lambda p: p["lastUpdated"], reverse=True)
            create_task(self.sidebar.triggerRefresh())

    async def connectProject(self, project):
        """
        Initializing connection to a project.
        """
        if not self.authenticated:
            create_task(self.sidebar.updateStatus("Not Authenticated to connect"))
            return

        anim_status = create_task(self._makeStatusAnimation("Connecting to Project"))

        # start connection
        anim_status.cancel()
        airlatexproject = AirLatexProject(await self._getWebSocketURL(), project, self.user_id, self.sidebar, cookie="; ".join(c.name + "=" + c.value for c in self.cj), wait_for=self.wait_for)
        create_task(airlatexproject.start())



