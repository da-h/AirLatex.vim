import browser_cookie3
import requests
import json
from bs4 import BeautifulSoup
import time
from threading import Thread
import re

cj = browser_cookie3.load()
DEBUG = False

# Generate a timstamp with a length of 13 numbers
def _genTimeStamp():
    t = time.time()
    t = str(t)
    t = t[:10]+t[11:]
    while len(t) < 13:
        t += "0"
    return t


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


from tornado.ioloop import IOLoop, PeriodicCallback
from tornado import gen
from tornado.websocket import websocket_connect
import asyncio
import re
# import nest_asyncio
# nest_asyncio.apply()
import time
from itertools import count


codere = re.compile("(\d):(?:(\d+)(\+?))?:(?::(?:(\d+)(\+?))?(.*))?")
# code, await_id, await_mult, answer_id, answer_mult, msg = codere.match(str).groups()
# code        : m[0]
# await_id    : m[1]
# await_mult  : m[2]
# answer_id   : m[3]
# answer_mult : m[5]
# msg         : m[5]

class AirLatexProject:

    def __init__(self,url, project, sidebar, session):
        project["handler"] = self
        self.url = url
        self.session = session
        self.project = project
        self.sidebar = sidebar
        self.url = url
        self.command_counter = count(1)
        self.ioloop = IOLoop()
        self.ws = None
        self.connect()
        PeriodicCallback(self.keep_alive, 20000).start()
        self.requests = {}
        self.cursors = {}
        self.documents = {}
        self.ioloop.start()

    def cleanup(self):
        self.disconnect()

    def send(self,message_type,message=None):
        if message_type == "keep_alive":
            self.ws.write_message("2::")
            return
        assert message is not None
        message_content = json.dumps(message) if isinstance(message, dict) else message
        if message_type == "update":
            self.ws.write_message("5:::"+message_content)
        elif message_type == "cmd":
            cmd_id = next(self.command_counter)
            self.ws.write_message("5:" + str(cmd_id) + "+::" + message_content)
            self.requests[str(cmd_id)] = message

    def triggerRefresh(self):
        if self.sidebar:
            self.sidebar.triggerRefresh()


    @gen.coroutine
    def sendOps(self, ops, document, hash):
        source = document["_id"]
        version = document["version"]
        self.send("cmd",{
            "name":"applyOtUpdate",
            "args": [
                document["_id"],
                {
                    "doc": document["_id"],
                    "meta": {
                        "hash": hash,
                        "source": source,
                        "ts": _genTimeStamp(),
                        "user_id": self.session.user_id
                    },
                    "op": ops,
                    "v": version
                }
            ]
        })

    @gen.coroutine
    def joinDocument(self, buffer):

        # register buffer in document
        # doc = buffer # FOR DEBUGGING
        # doc["buffer"] = Mock() # FOR DEBUGGING
        doc = buffer.document
        doc["buffer"] = buffer

        # register document in project_handler
        self.documents[doc["_id"]] = doc

        # regester for document-watching
        self.send("cmd",{
            "name":"joinDoc",
            "args": [
                doc["_id"],
                {"encodeRanges": True}
            ]
        })


    @gen.coroutine
    def disconnect(self):
        with open("/tmp/testclose","w") as f:
            f.write("closed2")
        IOLoop.instance().stop()
        self.ioloop.stop()
        self.project["msg"] = "Disconnected."
        self.project["open"] = False

    @gen.coroutine
    def connect(self):
        try:
            self.ws = yield websocket_connect(self.url)
        except Exception as e:
            self.project["msg"] = "Connection Error."
            self.triggerRefresh()
        else:
            self.project["msg"] = "Connected."
            self.triggerRefresh()
            self.run()

    @gen.coroutine
    def run(self):
        while True:
            msg = yield self.ws.read_message()
            if msg is None:
                self.project["msg"] = "Connection Closed."
                self.triggerRefresh()
                self.ws = None
                break

            # parse the code
            code, await_id, await_mult, answer_id, answer_mult, data = codere.match(msg).groups()
            if data:
                try:
                    data = json.loads(data)
                except:
                    data = {"name":"error"}

            # first message
            if code == "1":
                pass

            # keep alive
            elif code == "2":
                self.keep_alive()

            # server request
            elif code == "5":
                if not isinstance(data,dict):
                    pass

                # connection accepted => join Project
                if data["name"] == "connectionAccepted":
                    self.project["msg"] = "Connection Active."
                    self.send("cmd",{"name":"joinProject","args":[{"project_id":self.project["id"]}]})

                # broadcastDocMeta => we ignore it at first
                elif data["name"] == "broadcastDocMeta":
                    pass

                # client Connected => delete from cursor list
                elif data["name"] == "clientTracking.clientUpdated":
                    for cursor in data["args"]:
                        self.cursors[cursor["id"]] = cursor

                # client Disconnected => delete from cursor list
                elif data["name"] == "clientTracking.clientDisconnected":
                    for id in data["args"]:
                        if id in self.cursors:
                            del self.cursors[id]

                # update applied => apply update to buffer
                elif data["name"] == "otUpdateApplied":

                    # adapt version
                    if 'v' in data:
                        v = data['v']
                        if v >= self.documents[data["doc"]]:
                            self.document[data["doc"]] = v+1

                    # nothing to do?
                    if "args" not in data:
                        return

                    # apply update to buffer
                    for op in data["args"]:
                        self.documents[op["doc"]]["buffer"].applyUpdate(op)

                # error occured
                elif data["name"] == "otUpdateError":
                    self.project["msg"] = "Error occured on operation Update: " + data["args"][0]
                    self.disconnect()

                # unknown message
                else:
                    self.project["msg"] = "Data not known"

            # answer to our request
            elif code == "6":

                # get request command
                request = self.requests[answer_id]
                cmd = request["name"]

                # joinProject => server lists project information
                if cmd == "joinProject":
                    project_info = data[1]
                    self.project.update(project_info)
                    self.project["open"] = True
                    self.triggerRefresh()

                elif cmd == "joinDoc":
                    id = request["args"][0]
                    self.documents[id]["version"] = data[2]
                    self.documents[id]["buffer"].write(data[1])

                elif cmd == "applyOtUpdate":
                    del self.requests[answer_id]

                else:
                    # self.project["msg"] = "Data not known:"+str(msg)
                    self.project["msg"] = "no:"+str(request)

            # unknown message
            else:
                self.project["msg"] = msg


    def keep_alive(self):
        if self.ws is None:
            self.connect()
        else:
            self.send("keep_alive")


# for debugging
# if __name__ == "__main__":
#     from mock import Mock
#     import os
#     DOMAIN = os.environ["DOMAIN"]
#     sl = AirLatexSession(DOMAIN, None)
#     sl.login()
#     project = sl.projectList()[0]
#     print(project)
#     sl.connectProject(project)
#     time.sleep(3)
#     print(project)
#     doc = project["rootFolder"][0]["docs"][0]
#     project["handler"].joinDocument(doc)
#     time.sleep(3)
#     print("sending ops")
#     project["handler"].sendOps([{'p': 0, 'd': '0abB'}], doc)
