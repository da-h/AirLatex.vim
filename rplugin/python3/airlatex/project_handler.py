import pynvim
from tornado.ioloop import IOLoop, PeriodicCallback
from tornado import gen
from tornado.websocket import websocket_connect
import re
from itertools import count
import json
from airlatex.util import _genTimeStamp, getLogger
# from util import _genTimeStamp # FOR DEBUG MODE
# from mock import Mock # FOR DEBUG MODE
import time
from threading import Thread, currentThread, Lock

codere = re.compile(r"(\d):(?:(\d+)(\+?))?:(?::(?:(\d+)(\+?))?(.*))?")
# code, await_id, await_mult, answer_id, answer_mult, msg = codere.match(str).groups()
# code        : m[0]
# await_id    : m[1]
# await_mult  : m[2]
# answer_id   : m[3]
# answer_mult : m[5]
# msg         : m[5]

class AirLatexProject:

    def __init__(self, url, project, used_id, msg_queue, thread):
        project["handler"] = self
        self.msg_queue = msg_queue
        self.msg_thread = thread
        self.ioloop = IOLoop()
        self.url = url
        self.used_id = used_id
        self.project = project
        self.url = url
        self.command_counter = count(1)
        self.ws = None
        self.requests = {}
        self.cursors = {}
        self.documents = {}
        self.ops_await_accept = False
        self.ops_mutex = Lock()
        self.log = getLogger(__name__)

        PeriodicCallback(self.keep_alive, 20000).start()
        self.connect()
        self.ioloop.start()

    def cleanup(self):
        self.msg_thread.do_run = False
        self.disconnect()

    def send(self,message_type,message=None):
        if message_type == "keep_alive":
            self.ws.write_message("2::")
            return
        assert message is not None
        message_content = json.dumps(message) if isinstance(message, dict) else message
        if message_type == "update":
            self.log.debug("send update: "+message_content)
            self.ws.write_message("5:::"+message_content)
        elif message_type == "cmd":
            cmd_id = next(self.command_counter)
            msg = "5:" + str(cmd_id) + "+::" + message_content
            self.log.debug("send cmd: "+msg)
            self.ws.write_message(msg)
            self.requests[str(cmd_id)] = message

    def sidebarMsg(self, msg):
        self.msg_queue.put(("msg",None,msg))

    def bufferDo(self, doc_id, command, data):
        if doc_id in self.documents:
            self.msg_queue.put((command, self.documents[doc_id], data))

    def updateRemoteCursor(self, cursors):
        for cursor in cursors:
            if "row" in cursor and "column" in cursor and "doc_id" in cursor:
                self.bufferDo(cursor["doc_id"], "updateRemoteCursor", cursor)

    def updateCursor(self,doc, pos):
        self.send("update",{
            "name":"clientTracking.updatePosition",
            "args": [{
                "doc_id": doc["_id"],
                "row": pos[0]-1,
                "column": pos[1]
            }]
        })


    def sendOps(self, document, ops=[]):
        self.log.debug("sendOps(doc=%s, ops=%s)" % (document["_id"], str(len(ops))))

        with self.ops_mutex:

            # append new ops to buffer
            document["ops_buffer"] += ops

            # skip if nothing to do
            if len(document["ops_buffer"]) == 0:
                return

            # wait if awaiting server response
            if self.ops_await_accept:
                self.log.debug("Still Awaiting Accept!")
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
                            "user_id": self.used_id
                        },
                        "op": ops_buffer,
                        "v": document["version"]
                    }
                ]
            })

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

    def triggerSidebarRefresh(self):
        self.log.debug("triggerSidebarRefresh()")
        self.msg_queue.put(("refresh",None,None))

    def disconnect(self):
        self.log.debug("Connection Closed")
        IOLoop.instance().stop()
        self.ioloop.stop()
        self.sidebarMsg("Disconnected.")
        self.project["open"] = False
        self.project["connected"] = False

    @gen.coroutine
    def connect(self):
        try:
            self.project["connected"] = True
            self.ws = yield websocket_connect(self.url)
        except Exception as e:
            self.sidebarMsg("Connection Error: "+str(e))
        else:
            self.sidebarMsg("Connected.")
            self.run()

    @gen.coroutine
    def run(self):
        try:
            while True:
                msg = yield self.ws.read_message()
                # if msg is None:
                #     self.sidebarMsg("Connection Closed")
                #     self.ws = None
                #     break
                self.log.debug(msg)

                # parse the code
                code, await_id, await_mult, answer_id, answer_mult, data = codere.match(msg).groups()
                if data:
                    try:
                        data = json.loads(data)
                    except:
                        data = {"name":"error"}

                # error occured
                if code == "0":
                    self.sidebarMsg("The server closed the connection.")
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
                        self.sidebarMsg("Connection Active.")
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
                            self.bufferDo(op["doc"], "applyUpdate", op)

                    # error occured
                    elif data["name"] == "otUpdateError":
                        self.sidebarMsg("Error occured on operation Update: " + data["args"][0])
                        self.disconnect()

                    # unknown message
                    else:
                        self.sidebarMsg("Data not known: "+msg)

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
                        self.triggerSidebarRefresh()

                    elif cmd == "joinDoc":
                        id = request["args"][0]
                        self.documents[id]["version"] = data[2]
                        self.bufferDo(id, "write", [d.encode("latin1").decode("utf8") for d in data[1]])

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
                        self.sidebarMsg("Data not known:"+str(msg))

                # unknown message
                else:
                    self.sidebarMsg("Unknown Code:"+str(msg))
        except (gen.Return, StopIteration):
            raise
        except Exception as e:
            self.sidebarMsg("Error: "+type(e)+" "+str(e))
            raise


    def keep_alive(self):
        if self.ws is None:
            self.connect()
        else:
            self.send("keep_alive")

