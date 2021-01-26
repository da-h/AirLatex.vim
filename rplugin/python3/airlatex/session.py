import pynvim
import browser_cookie3
import requests
import json
import time
import tempfile
from threading import Thread, currentThread
from queue import Queue
from os.path import expanduser
import re
from airlatex.project_handler import AirLatexProject
from airlatex.util import _genTimeStamp, getLogger
from http.cookiejar import CookieJar


import traceback
def catchException(fn):
    def wrapped(self, nvim, *args, **kwargs):
        try:
            return fn(self, nvim, *args, **kwargs)
        except Exception as e:
            self.log.exception(str(e))
            nvim.err_write(str(e)+"\n")
            raise e
    return wrapped


### All web page related airlatex stuff
class AirLatexSession:
    def __init__(self, domain, servername, sidebar, https=True):
        self.sidebar = sidebar
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

    @catchException
    def cleanup(self, nvim):
        self.log.debug("cleanup()")
        for p in self.cached_projectList:
            if "handler" in p:
                p["handler"].disconnect()
        for t in self.projectThreads:
            t.do_run = False
        self.projectThreads = []

    @catchException
    def login(self, nvim):
        self.log.debug("login()")
        if not self.authenticated:
            self.updateStatus(nvim, "Connecting")

            browser   = nvim.eval("g:AirLatexCookieBrowser")

            # guess cookie dir (browser_cookie3 does that already mostly)
            self.log.debug("Checking Browser '%s'" % browser)

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
                    self.log.debug("Found cookie " + str(c))
                    self.cj.set_cookie(c)
            self.cj_str = "; ".join(c.name + "=" + c.value for c in self.cj)

            # check if cookie found by testing if projects redirects to login page
            try:
                self.log.debug("Got cookie.")
                redirect  = self.httpHandler.get(self.url + "/project", cookies=self.cj)
                if redirect.ok:
                    self.log.debug("Got project list")
                    self.authenticated = True
                    self.updateProjectList(nvim)
                    return True
                else:
                    self.log.debug("Could not fetch '%s/project'. Response chain: %s" % (self.url, str(redirect)))
                    with tempfile.NamedTemporaryFile(delete=False) as f:
                        f.write(redirect.text.encode())
                        self.updateStatus(nvim, "Connection failed: I could not retrieve the project list. You can check the response page under: %s" % f.name)
                    return False
            except Exception as e:
                self.updateStatus(nvim, "Connection failed: "+str(e))
        else:
            return False

    # Returns a list of airlatex projects
    # @catchException
    def projectList(self):
        return self.cached_projectList

    @catchException
    def updateProjectList(self, nvim):
        self.log.debug("updateProjectList()")
        if self.authenticated:

            def loading(self, nvim):
                i = 0
                t = currentThread()
                while getattr(t, "do_run", True):
                    s = " .." if i%3 == 0 else ". ." if i%3 == 1 else ".. "
                    self.updateStatus(nvim, s+" Loading "+s)
                    i += 1
                    time.sleep(0.1)
            thread = Thread(target=loading, args=(self,nvim), daemon=True)
            thread.start()

            projectPage = self.httpHandler.get(self.url + "/project", cookies=self.cj).text
            thread.do_run = False
            pos_script_1  = projectPage.find("<script id=\"data\"")
            pos_script_2 = projectPage.find(">", pos_script_1 + 20)
            pos_script_close = projectPage.find("</script", pos_script_2 + 1)
            if pos_script_1 == -1 or pos_script_2 == -1 or pos_script_close == -1:
                with tempfile.NamedTemporaryFile(delete=False) as f:
                    f.write(projectPage.encode())
                    self.updateStatus(nvim, "Offline. Please Login. I saved the webpage '%s' I got under %s" % (self.url, f.name))
                return []
            data = projectPage[pos_script_2+1:pos_script_close]
            data = json.loads(data)
            self.user_id = re.search("user_id\s*:\s*'([^']+)'",projectPage)[1]
            self.updateStatus(nvim, "Online")

            self.cached_projectList = data["projects"]
            self.cached_projectList.sort(key=lambda p: p["lastUpdated"], reverse=True)
            self.triggerRefresh(nvim)

    # Returns a list of airlatex projects
    @catchException
    def connectProject(self, nvim, project):
        if self.authenticated:

            # This is needed because IOLoop and pynvim interfere!
            msg_queue = Queue()
            msg_queue.put(("msg",None,"Connecting Project"))
            project["msg_queue"] = msg_queue
            def flush_queue(queue, project, servername):
                t = currentThread()
                nvim = pynvim.attach("socket",path=servername)
                while getattr(t, "do_run", True):
                    cmd, doc, data = queue.get()
                    try:
                        if cmd == "msg":
                            self.log.debug("msg_queue : "+data)
                            project["msg"] = data
                            nvim.command("call AirLatex_SidebarRefresh()")
                            continue
                        elif cmd == "await":
                            project["await"] = data
                            nvim.command("call AirLatex_SidebarRefresh()")
                            continue
                        elif cmd == "refresh":
                            self.triggerRefresh(nvim)
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
                        nvim.command("call AirLatex_SidebarRefresh()")
            msg_thread = Thread(target=flush_queue, args=(msg_queue, project, self.servername), daemon=True)
            msg_thread.start()
            self.projectThreads.append(msg_thread)

            # start connection
            def initProject():
                nvim = pynvim.attach("socket",path=self.servername)
                try:
                    AirLatexProject(self._getWebSocketURL(), project, self.user_id, msg_queue, msg_thread, cookie=self.cj_str)
                except Exception as e:
                    self.log.error(traceback.format_exc(e))
                    nvim.err_write(traceback.format_exc(e)+"\n")
            thread = Thread(target=initProject,daemon=True)
            self.projectThreads.append(thread)
            thread.start()

    @catchException
    def updateStatus(self, nvim, msg):
        self.log.debug_gui("updateStatus("+msg+")")
        self.status = msg
        nvim.command("call AirLatex_SidebarUpdateStatus()")

    @catchException
    def triggerRefresh(self, nvim):
        self.log.debug_gui("triggerRefresh()")
        nvim.command("call AirLatex_SidebarRefresh()")

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



