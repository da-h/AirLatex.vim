from tornado.ioloop import IOLoop, PeriodicCallback
from tornado import gen
from tornado.websocket import websocket_connect
import asyncio
import re
import time
from itertools import count
import json
# from mock import Mock # FOR DEBUG MODE


# Generate a timstamp with a length of 13 numbers
def _genTimeStamp():
    t = time.time()
    t = str(t)
    t = t[:10]+t[11:]
    while len(t) < 13:
        t += "0"
    return t



codere = re.compile(r"(\d):(?:(\d+)(\+?))?:(?::(?:(\d+)(\+?))?(.*))?")
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
        self.ops_await_accept = False

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
            msg = "5:" + str(cmd_id) + "+::" + message_content
            self.ws.write_message(msg)
            self.requests[str(cmd_id)] = message

    def triggerRefresh(self):
        if self.sidebar:
            self.sidebar.triggerRefresh()

    def updateRemoteCursor(self, cursors):
        for cursor in cursors:
            if "row" in cursor and "column" in cursor and "doc_id" in cursor and cursor["doc_id"] in self.documents:
                self.documents[cursor["doc_id"]].updateRemoteCursor(cursor)

    @gen.coroutine
    def updateCursor(self,doc, pos):
        self.send("cmd",{
            "name":"clientTracking.updatePosition",
            "args": [{
                "doc_id": doc["_id"],
                "row": pos[0]-1,
                "column": pos[1]
            }]
        })


    @gen.coroutine
    def sendOps(self, document, ops=[]):

        # append new ops to buffer
        document["ops_buffer"] += ops

        # skip if nothing to do
        if len(document["ops_buffer"]) == 0:
            return

        # wait if awaiting server response
        if self.ops_await_accept:
            return

        # clean buffer for next call
        ops_buffer, document["ops_buffer"], self.ops_await_accept = document["ops_buffer"], [], True

        # actually send operations
        source = document["_id"]
        self.send("cmd",{
            "name":"applyOtUpdate",
            "args": [
                document["_id"],
                {
                    "doc": document["_id"],
                    "meta": {
                        # "hash": hash, # it feels like they do not use the hash anyway (who nows what hash they need) ;)
                        "source": source,
                        "ts": _genTimeStamp(),
                        "user_id": self.session.user_id
                    },
                    "op": ops_buffer,
                    "v": document["version"]
                }
            ]
        })

    @gen.coroutine
    def joinDocument(self, buffer):

        # register buffer in document
        # doc = buffer # FOR DEBUG MODE
        # doc["buffer"] = Mock() # FOR DEBUG MODE
        doc = buffer.document
        doc["buffer"] = buffer

        # register document in project_handler
        self.documents[doc["_id"]] = doc

        # register document op-buffer
        self.documents[doc["_id"]]["ops_buffer"] = []

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
        else:
            self.project["msg"] = "Connected."
            self.run()

    @gen.coroutine
    def run(self):
        while True:
            msg = yield self.ws.read_message()
            msg = msg
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

            # error occured
            if code == "0":
                self.project["msg"] = "The server closed the connection."
                self.disconnect()

            # first message
            elif code == "1":
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
                    self.send("cmd",{"name":"clientTracking.getConnectedUsers"})

                # broadcastDocMeta => we ignore it at first
                elif data["name"] == "broadcastDocMeta":
                    pass

                # client Connected => delete from cursor list
                elif data["name"] == "clientTracking.clientUpdated":
                    for cursor in data["args"]:
                        self.cursors[cursor["id"]].update(cursor)
                    self.updateRemoteCursor(data["args"])

                # client Disconnected => delete from cursor list
                elif data["name"] == "clientTracking.clientDisconnected":
                    for id in data["args"]:
                        if id in self.cursors:
                            del self.cursors[id]
                    self.updateRemoteCursor(data["args"])

                # update applied => apply update to buffer
                elif data["name"] == "otUpdateApplied":

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
                    self.project["msg"] = "Data not known: "+msg

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

                elif cmd == "joinDoc":
                    id = request["args"][0]
                    self.documents[id]["version"] = data[2]
                    self.documents[id]["buffer"].write([d.encode("latin1").decode("utf8") for d in data[1]])

                elif cmd == "applyOtUpdate":
                    id = request["args"][0]

                    # increase version as update was accepted
                    self.documents[id]["version"] += 1

                    # flush next
                    self.ops_await_accept = False
                    self.sendOps(self.documents[id])

                    # remove awaiting request
                    del self.requests[answer_id]

                elif cmd == "clientTracking.getConnectedUsers":
                    for cursor in data[1]:
                        if "cursorData" in cursor:
                            cursorData = cursor["cursorData"]
                            del cursor["cursorData"]
                            cursor.update(cursorData)
                        self.cursors[cursor["client_id"]] = cursor
                    self.updateRemoteCursor(data[1])

                elif cmd == "clientTracking.updatePosition":
                    # server accepted the change
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

