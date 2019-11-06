import browser_cookie3
import requests
import json
from bs4 import BeautifulSoup
import time
from threading import Thread
import re
from python.project_handler import AirLatexProject, _genTimeStamp
# from project_handler import AirLatexProject, _genTimeStamp # DEBUG

cj = browser_cookie3.load()
DEBUG = False


### All web page related airlatex stuff
class AirLatexSession:
    def __init__(self, domain, sidebar):
        self.sidebar = sidebar
        self.domain = domain
        self.url = "https://"+domain
        self.authenticated = False
        self.httpHandler = requests.Session()
        self.cached_projectList = None
        self.projectThreads = []
        self.status = "Connecting ..."

    def cleanup(self):
        for p in self.cached_projectList:
            if "handler" in p:
                p["handler"]
        for t in self.projectThreads:
            t.stop()

    def login(self):
        if not self.authenticated:
            # check if cookie found by testing if projects redirects to login page
            redirect  = self.httpHandler.get(self.url + "/projects", cookies=cj)
            if len(redirect.history) == 0:
                self.authenticated = True
                return True
            else:
                return False
        else:
            return False

    # Returns a list of airlatex projects
    def projectList(self):
        if self.authenticated:

            # use cache, if exists
            if self.cached_projectList is not None:
                return self.cached_projectList

            self.status = "Connecting to "+self.url
            self.triggerRefresh()

            projectPage = self.httpHandler.get(self.url + "/project")
            projectSoup = BeautifulSoup(projectPage.text, features='lxml')
            data = projectSoup.findAll("script",attrs={'id':'data'})
            if len(data) == 0:
                self.status = "Offline. Please Login."
                return []
            data = json.loads(data[0].text)
            self.user_id = re.search("user_id\s*:\s*'([^']+)'",projectPage.text)[1]
            self.status = "Online"

            self.cached_projectList = data["projects"]
            self.cached_projectList.sort(key=lambda p: p["lastUpdated"], reverse=True)
            return self.cached_projectList

    # Returns a list of airlatex projects
    def connectProject(self, project):
        if self.authenticated:
            projectId = project["id"]

            # message for the user
            project["msg"] = "Connecting Project ..."
            self.triggerRefresh()

            # start connection
            def initProject(project, sidebar):
                AirLatexProject(self._getWebSocketURL(), project, self.sidebar, self)
            thread = Thread(target=initProject,args=(project,self.sidebar), daemon=True)
            thread.start()
            self.projectThreads.append(thread)

    def triggerRefresh(self):
        if self.sidebar:
            self.sidebar.triggerRefresh()


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
    async def main():
        sl = AirLatexSession(DOMAIN, None)
        sl.login()
        project = sl.projectList()[0]
        print(">>>>",project)
        sl.connectProject(project)
        time.sleep(3)
        print(">>>",project)
        doc = project["rootFolder"][0]["docs"][0]
        project["handler"].joinDocument(doc)
        time.sleep(3)
        print(">>>> sending ops")
        project["handler"].sendOps(doc, [{'p': 0, 'i': '0abB\n'}])
        project["handler"].sendOps(doc, [{'p': 0, 'i': 'def\n'}])
        project["handler"].sendOps(doc, [{'p': 0, 'i': 'def\n'}])

    asyncio.run(main())
