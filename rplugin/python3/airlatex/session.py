import pynvim
import browser_cookie3
import requests
import json
import time
from threading import Thread, currentThread
from asyncio import Lock, sleep
from queue import Queue
import re
from airlatex.project_handler import AirLatexProject
from airlatex.util import _genTimeStamp, getLogger
# from project_handler import AirLatexProject # FOR DEBUG MODE
# from util import _genTimeStamp # FOR DEBUG MODE

cj = browser_cookie3.load()


import traceback
def catchException(fn):
    def wrapped(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except Exception as e:
            self.log.exception(str(e))
            self.nvim.err_write(str(e)+"\n")
            raise e
    return wrapped


### All web page related airlatex stuff
class AirLatexSession:
    def __init__(self, domain, servername, sidebar, nvim):
        self.sidebar = sidebar
        self.nvim = nvim
        self.servername = servername
        self.domain = domain
        self.url = "https://"+domain
        self.authenticated = False
        self.httpHandler = requests.Session()
        self.cached_projectList = []
        self.projectThreads = []
        self.status = ""
        self.log = getLogger(__name__)

    @catchException
    def cleanup(self):
        self.log.debug("cleanup()")
        for p in self.cached_projectList:
            if "handler" in p:
                p["handler"].disconnect()
        for t in self.projectThreads:
            t.do_run = False
        self.projectThreads = []

    @catchException
    async def login(self):
        self.log.debug("login()")
        if not self.authenticated:
            await self.updateStatus("Connecting")
            # check if cookie found by testing if projects redirects to login page
            try:
                get = lambda: self.httpHandler.get(self.url + "/project", cookies=cj)
                redirect = await self.nvim.loop.run_in_executor(None, get)
                if len(redirect.history) == 0:
                    self.authenticated = True
                    await self.updateProjectList()
                    return True
                else:
                    return False
            except Exception as e:
                await self.updateStatus("Connection failed: "+str(e))
        else:
            return False

    # Returns a list of airlatex projects
    # @catchException
    def projectList(self):
        return self.cached_projectList

    @catchException
    async def updateProjectList(self):
        self.log.debug("updateProjectList()")
        if self.authenticated:

            stop = Lock()
            await stop.acquire()
            async def loading(self, stop):
                i = 0
                while stop.locked():
                    s = " .." if i%3 == 0 else ". ." if i%3 == 1 else ".. "
                    await self.updateStatus(s+" Loading "+s)
                    i += 1
            self.nvim.loop.create_task(loading(self, stop))

            get = lambda: self.httpHandler.get(self.url + "/project", cookies=cj)
            projectPage = (await self.nvim.loop.run_in_executor(None, get)).text
            projectPage = self.httpHandler.get(self.url + "/project").text
            redirect = await self.nvim.loop.run_in_executor(None, requests.get, 'http://www.google.com')
            pos_script_1  = projectPage.find("<script id=\"data\"")
            pos_script_2 = projectPage.find(">", pos_script_1 + 20)
            pos_script_close = projectPage.find("</script", pos_script_2 + 1)
            stop.release()
            if pos_script_1 == -1 or pos_script_2 == -1 or pos_script_close == -1:
                await self.updateStatus("Offline. Please Login.")
                return []
            data = projectPage[pos_script_2+1:pos_script_close]
            data = json.loads(data)
            self.user_id = re.search("user_id\s*:\s*'([^']+)'",projectPage)[1]
            await self.updateStatus("Online")

            self.cached_projectList = data["projects"]
            self.cached_projectList.sort(key=lambda p: p["lastUpdated"], reverse=True)
            await self.triggerRefresh()

    # Returns a list of airlatex projects
    @catchException
    def connectProject(self, project):
        if self.authenticated:

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
                            # self.triggerRefresh()
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
            def initProject():
                nvim = pynvim.attach("socket",path=self.servername)
                try:
                    AirLatexProject(self._getWebSocketURL(), project, self.user_id, msg_queue, msg_thread)
                except Exception as e:
                    self.log.error(traceback.format_exc(e))
                    nvim.err_write(traceback.format_exc(e)+"\n")
            thread = Thread(target=initProject,daemon=True)
            self.projectThreads.append(thread)
            thread.start()

    @catchException
    async def updateStatus(self, msg):
        self.log.debug_gui("updateStatus("+msg+")")
        self.status = msg
        await self.sidebar.triggerRefresh(False)
        await sleep(0.1)

    @catchException
    async def triggerRefresh(self):
        self.log.debug_gui("triggerRefresh()")
        await self.sidebar.triggerRefresh()

    def _getWebSocketURL(self):
        if self.authenticated:
            # Generating timestamp
            timestamp = _genTimeStamp()

            # To establish a websocket connection
            # the client must query for a sec url
            self.httpHandler.get(self.url + "/project")
            channelInfo = self.httpHandler.get(self.url + "/socket.io/1/?t="+timestamp)
            wsChannel = channelInfo.text[0:channelInfo.text.find(":")]
            return "wss://" + self.domain + "/socket.io/1/websocket/"+wsChannel



# for debugging
if __name__ == "__main__":
    import asyncio
    from mock import Mock
    import os
    DOMAIN = os.environ["DOMAIN"]
    sidebar = Mock()
    nvim = Mock()
    pynvim = Mock()
    async def main():
        sl = AirLatexSession(DOMAIN, None, sidebar)
        sl.login(nvim)
        project = sl.projectList()[1]
        print(">>>>",project)
        sl.connectProject(nvim, project)
        time.sleep(3)
        # print(">>>",project)
        doc = project["rootFolder"][0]["docs"][0]
        project["handler"].joinDocument(doc)
        time.sleep(6)
        print(">>>> sending ops")
        # project["handler"].sendOps(doc, [{'p': 0, 'i': '0abB\n'}])
        # project["handler"].sendOps(doc, [{'p': 0, 'i': 'def\n'}])
        # project["handler"].sendOps(doc, [{'p': 0, 'i': 'def\n'}])

    asyncio.run(main())
