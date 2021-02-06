import pynvim
import browser_cookie3
import requests
import json
import time
import tempfile
from threading import Thread, currentThread
from asyncio import Lock, sleep, run_coroutine_threadsafe, create_task
from queue import Queue
from os.path import expanduser
import re
from airlatex.project_handler import AirLatexProject
from airlatex.util import _genTimeStamp, getLogger
from http.cookiejar import CookieJar



### All web page related airlatex stuff
class AirLatexSession:
    def __init__(self, domain, servername, sidebar, nvim, https=True):
        self.sidebar = sidebar
        self.nvim = nvim
        self.servername = servername
        self.domain = domain
        self.https = True if https else False
        self.url = ("https://" if https else "http://") + domain
        self.authenticated = False
        self.httpHandler = requests.Session()
        self.cached_projectList = []
        self.projectThreads = []
        self.status = ""
        self.log = getLogger(__name__)

        # guess cookie dir (browser_cookie3 does that already mostly)
        browser   = nvim.eval("g:AirLatexCookieBrowser")
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
        self.cj_str = "; ".join(c.name + "=" + c.value for c in self.cj)

    def cleanup(self):
        self.log.debug("cleanup()")
        for p in self.cached_projectList:
            if "handler" in p:
                p["handler"].disconnect()
        for t in self.projectThreads:
            t.do_run = False
        self.projectThreads = []


    # performs a loading animation until lock is released
    async def _makeStatusAnimation(self, str):
        i = 0
        while True:
            s = " .." if i%3 == 0 else ". ." if i%3 == 1 else ".. "
            await self.updateStatus(s + " " + str + " " + s)
            i += 1

    async def login(self):
        self.log.debug("login()")
        if not self.authenticated:
            anim_status = create_task(self._makeStatusAnimation("Connecting"))

            # check if cookie found by testing if projects redirects to login page
            try:
                get = lambda: self.httpHandler.get(self.url + "/project", cookies=self.cj)
                redirect = await self.nvim.loop.run_in_executor(None, get)
                anim_status.cancel()
                if redirect.ok:
                    self.authenticated = True
                    await self.updateProjectList()
                    return True
                else:
                    self.log.debug("Could not fetch '%s/project'. Response chain: %s" % (self.url, str(redirect)))
                    with tempfile.NamedTemporaryFile(delete=False) as f:
                        f.write(redirect.text.encode())
                        await self.updateStatus("Connection failed: I could not retrieve the project list. You can check the response page under: %s" % f.name)
                    return False
            except Exception as e:
                await self.updateStatus("Connection failed: "+str(e))
        else:
            return False

    # Returns a list of airlatex projects
    def projectList(self):
        return self.cached_projectList

    async def updateProjectList(self):
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
                    await self.updateStatus("Offline. Please Login. I saved the webpage '%s' I got under %s" % (self.url, f.name))
                return []
            data = projectPage[pos_script_2+1:pos_script_close]
            data = json.loads(data)
            self.user_id = re.search("user_id\s*:\s*'([^']+)'",projectPage)[1]
            await self.updateStatus("Online")

            self.cached_projectList = data["projects"]
            self.cached_projectList.sort(key=lambda p: p["lastUpdated"], reverse=True)
            await self.triggerRefresh()

    # Returns a list of airlatex projects
    async def connectProject(self, project):
        if not self.authenticated:
            await self.UpdateStatus("Not Authenticated to connect")
            return

        anim_status = create_task(self._makeStatusAnimation("Connecting to Project"))

        # This is needed because IOLoop and pynvim interfere!
        msg_queue = Queue()
        msg_queue.put(("msg",None,"Connecting Project"))
        project["msg_queue"] = msg_queue
        def flush_queue(queue, project, servername):
            t = currentThread()
            self.nvim = pynvim.attach("socket",path=servername)
            while getattr(t, "do_run", True):
                cmd, doc, data = queue.get()
                try:
                    if cmd == "msg":
                        self.log.debug("msg_queue : "+data)
                        project["msg"] = data
                        # nvim.command("call AirLatex_SidebarRefresh()")
                        continue
                    elif cmd == "await":
                        project["await"] = data
                        # nvim.command("call AirLatex_SidebarRefresh()")
                        continue
                    elif cmd == "refresh":
                        self.triggerRefresh()
                        continue

                    buf = doc["buffer"]
                    self.log.debug("cmd="+cmd)
                    if cmd == "applyUpdate":
                        buf.applyUpdate(data)
                    elif cmd == "write":
                        buf.write(data)
                    elif cmd == "updateRemoteCursor":
                        buf.updateRemoteCursor(data)
                except Exception as e:
                    self.log.error("Exception"+str(e))
                    project["msg"] = "Exception:"+str(e)
                    # nvim.command("call AirLatex_SidebarRefresh()")
        msg_thread = Thread(target=flush_queue, args=(msg_queue, project, self.servername), daemon=True)
        msg_thread.start()
        self.projectThreads.append(msg_thread)

        # start connection
        try:
            anim_status.cancel()
            self.log.debug("creating airlatexproject")
            airlatexproject = AirLatexProject(self._getWebSocketURL(), project, self.user_id, msg_queue, msg_thread, cookie=self.cj_str)
            self.log.debug("starting airlatexproject")
            create_task(airlatexproject.start())
            self.log.debug("starting airlatexproject done")
        except Exception as e:
            self.log.error(traceback.format_exc(e))
            self.nvim.err_write(traceback.format_exc(e)+"\n")

    async def updateStatus(self, msg):
        self.log.debug_gui("updateStatus("+msg+")")
        self.status = msg
        await self.sidebar.triggerRefresh(False)
        await sleep(0.1)

    async def triggerRefresh(self):
        self.log.debug_gui("triggerRefresh()")
        await self.sidebar.triggerRefresh()

    def _getWebSocketURL(self):
        if self.authenticated:
            # Generating timestamp
            timestamp = _genTimeStamp()

            # To establish a websocket connection
            # the client must query for a sec url
            self.httpHandler.get(self.url + "/project", cookies=self.cj)
            # channelInfo = self.httpHandler.get(self.url + "/socket.io/1/?t="+timestamp)
            channelInfo = self.httpHandler.get(self.url + "/socket.io/1/?t="+timestamp, cookies=self.cj)
            self.log.debug("Websocket channelInfo '%s'"%channelInfo.text)
            wsChannel = channelInfo.text[0:channelInfo.text.find(":")]
            self.log.debug("Websocket wsChannel '%s'"%wsChannel)
            return ("wss://" if self.https else "ws://") + self.domain + "/socket.io/1/websocket/"+wsChannel



