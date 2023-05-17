import pynvim
from tornado.ioloop import IOLoop, PeriodicCallback
from tornado import gen
from tornado.websocket import websocket_connect
import re
from itertools import count
import json
from airlatex.util import _genTimeStamp, generateId
import time
from tornado.locks import Lock, Event
from logging import DEBUG
from tornado.httpclient import HTTPRequest
from asyncio import Queue, wait_for, TimeoutError
from logging import getLogger
from asyncio import sleep, create_task
import requests

from datetime import datetime

from http.cookies import SimpleCookie

from intervaltree import Interval, IntervalTree

codere = re.compile(r"(\d):(?:(\d+)(\+?))?:(?::(?:(\d+)(\+?))?(.*))?")
# code, await_id, await_mult, answer_id, answer_mult, msg = codere.match(str).groups()
# code        : m[0]
# await_id    : m[1]
# await_mult  : m[2]
# answer_id   : m[3]
# answer_mult : m[5]
# msg         : m[5]

# Add a comment
# Post to /project/>project id>/thread/<gen id>/messages
# Get WS update
# broadcast location in apply
# get confirmation


class AirLatexProject:

  def __init__(
      self,
      url,
      project,
      csrf,
      session,
      cookie=None,
      wait_for=15,
      validate_cert=True):
    project["handler"] = self

    self.url = url
    self.project = project
    self.csrf = csrf

    self.sidebar = session.sidebar
    self.session = session
    self.session_id = None

    self.cookie = cookie
    self.wait_for = wait_for if str(wait_for).isnumeric() else None
    self.validate_cert = validate_cert

    self.command_counter = count(1)
    self.ws = None
    self.requests = {}
    self.cursors = {}
    self.documents = {}
    self.log = getLogger("AirLatex")
    self.ops_queue = Queue()
    self.pending_comments = {}
    self.connection_lock = Lock()
    self.heartbeat = PeriodicCallback(self.keep_alive, 20000)

  async def start(self):
    self.log.debug("Starting connection to server.")
    await self.connect()

  async def send(self, message_type, message=None, event=None):
    try:
      if message_type == "keep_alive":
        self.log.debug("Send keep_alive.")
        self.ws.write_message("2::")
        return
      assert message is not None
      message_content = json.dumps(message) if isinstance(
          message, dict) else message
      message["event"] = event
      if message_type == "update":
        self.log.debug("Sending update: " + message_content)
        self.ws.write_message("5:::" + message_content)
      elif message_type == "cmd":
        cmd_id = next(self.command_counter)
        msg = "5:" + str(cmd_id) + "+::" + message_content
        self.log.debug("Sendng cmd: " + msg)
        self.requests[str(cmd_id)] = message
        self.ws.write_message(msg)
    except Exception as e:
      await self.sidebarMsg("Error: " + type(e).__name__ + ": " + str(e))
      await self.disconnect(
          f"Send failed ({type(e).__name__}): {e}")
      raise

  async def sidebarMsg(self, msg):
    self.log.debug_gui("sidebarMsg: %s" % msg)
    self.project["msg"] = msg
    await self.sidebar.triggerRefresh()

  async def gui_await(self, waiting=True):
    self.project["await"] = waiting
    await self.sidebar.triggerRefresh()

  async def bufferDo(self, doc_id, command, data):
    if doc_id in self.documents:
      doc = self.documents[doc_id]
      buf = doc["buffer"]
      self.log.debug_gui("bufferDo cmd=" + command)
      if command == "applyUpdate":
        buf.applyUpdate(data, self.comments)
      elif command == "write":
        buf.write(data)
      elif command == "updateRemoteCursor":
        buf.updateRemoteCursor(data)
      elif command == "clearRemoteCursor":
        buf.clearRemoteCursor(data)
      elif command == "highlightComments":
        await buf.highlightComments(self.comments, data)

  async def syncGit(self, message):
    self.log.debug(f"Syncing. {str(self.project)}")
    # https://www.overleaf.com/project/<project>/github-sync/merge
    compile_url = f"{self.session.url}/project/{self.project['id']}/github-sync/merge"
    post = lambda: self.session.httpHandler.post(
        compile_url,
        headers={
            'Cookie': self.cookie,
            'x-csrf-token': self.csrf,
            'content-type': 'application/json'
        },
        json={
          "message": message
        })
    response = (await self.session.nvim.loop.run_in_executor(None, post))
    try:
      assert response.status_code == 200, f"Bad status code {response.status_code}"
      self.log.debug("Synced.")
    except Exception as e:
      self.log.debug("\nCompilation response content:")
      self.log.debug(f"{response.content}\n---\n{e}")

  async def compile(self):
    self.log.debug(f"Compiling. {str(self.project)}")
    compile_url = f"{self.session.url}/project/{self.project['id']}/compile?enable_pdf_caching=true"
    post = lambda: self.session.httpHandler.post(
        compile_url,
        headers={
            'Cookie': self.cookie,
            'x-csrf-token': self.csrf,
            'content-type': 'application/json'
        },
        json={
            "rootDoc_id": self.project["rootDoc_id"],
            "draft": False,
            "check": "silent",
            "incrementalCompilesEnabled": True,
            "stopOnFirstError": False
        })
    logger = self.log
    response = (await self.session.nvim.loop.run_in_executor(None, post))

    try:
      data = response.json()
      if data["status"] != "success":
        raise Exception("No success in compiling. Something failed.")
      logger.debug("Compiled.")
    except Exception as e:
      logger.debug("\nCompilation response content:")
      logger.debug(f"{response.content}\n---\n{e}")

  async def adjustComment(
      self, thread, state, content="", resolve_state=None, retract=False):
    resolve_url = f"{self.session.url}/project/{self.project['id']}/thread/{thread}/{state}"
    payload = {"_csrf": self.csrf}
    if content:
      payload["content"] = content
    post = lambda: self.session.httpHandler.post(
        resolve_url, headers={
            'Cookie': self.cookie,
        }, json=payload)
    logger = self.log
    response = (await self.session.nvim.loop.run_in_executor(None, post))
    logger.debug(f"adjusting comment to {state}")
    try:
      assert response.status_code == 204, f"Bad status code {response.status_code}"
      # We'll get a websocket confirmation, and handle it from there.
      # Nothing else to do
    except Exception as e:
      logger.debug("\n {state} response content:")
      logger.debug(f"{response.content}\n---\n{e}")
      if resolve_state is not None:
        self.comments.get(thread, {})["resolved"] = resolve_state
      if retract:
        del self.comments[thread]

  def resolveComment(self, thread):
    self.comments.get(thread, {})["resolved"] = True
    create_task(self.adjustComment(thread, "resolve", resolve_state=False))

  def reopenComment(self, thread):
    self.comments.get(thread, {})["resolved"] = False
    create_task(self.adjustComment(thread, "reopen", resolve_state=True))

  def replyComment(self, thread, content):
    self.comments.get(thread, {}).get("messages", []).append(
        {
            "user": {
                "first_name": "** (pending)"
            },
            "content": content,
            "timestamp": datetime.now().timestamp()
        })
    create_task(self.adjustComment(thread, "messages", content))

  def createComment(self, thread, doc_id, content):
    doc = self.documents[doc_id]["buffer"]
    interval = doc.comment_selection[:].pop()
    count = interval.begin
    highlight = "\n".join(doc.buffer[:])[interval.begin:interval.end]
    if not content or not highlight:
      return
    self.comments[thread] = {
        "messages":
            [
                {
                    "user": {
                        "first_name": "** (pending)"
                    },
                    "content": content,
                    "timestamp": datetime.now().timestamp()
                }
            ]
    }
    self.pending_comments[thread] = (doc_id, count, highlight)
    create_task(self.adjustComment(thread, "messages", content, retract=True))

  async def getComments(self):
    comment_url = f"{self.session.url}/project/{self.project['id']}/threads"
    get = lambda: self.session.httpHandler.get(
        comment_url, headers={
            'Cookie': self.cookie,
        })
    logger = self.log
    response = (await self.session.nvim.loop.run_in_executor(None, get))
    try:
      comments = response.json()
      logger.debug("Got comments")
      return comments
    except Exception as e:
      logger.debug("\nComments response content:")
      logger.debug(f"{response.content}\n---\n{e}")

  async def clearRemoteCursor(self, session_id):
    for document in self.documents:
      await self.bufferDo(id, "clearRemoteCursor", session_id)

  async def updateRemoteCursor(self, cursors):
    for cursor in cursors:
      if "row" in cursor and "column" in cursor and "doc_id" in cursor:
        await self.bufferDo(cursor["doc_id"], "updateRemoteCursor", cursor)

  async def updateCursor(self, doc, pos):
    event = Event()
    await self.send(
        "update", {
            "name":
                "clientTracking.updatePosition",
            "args":
                [{
                    "doc_id": doc["_id"],
                    "row": pos[0] - 1,
                    "column": pos[1]
                }]
        },
        event=event)

  # wrapper for the ioloop
  async def sendOps(self, document, content_hash, ops=[], track=False):
    await self.ops_queue.put((document, content_hash, ops, track, False))

  # actual sending of ops
  async def _sendOps(self, document, content_hash, ops=[], track=False):

    # append new ops to buffer
    document["ops_buffer"] += ops

    # skip if nothing to do
    if len(document["ops_buffer"]) == 0:
      return

    # wait if awaiting server response
    event = Event()
    await self.gui_await(True)

    # clean buffer for next call
    ops_buffer, document["ops_buffer"] = document["ops_buffer"], []

    # actually send operations
    source = document["_id"]

    obj_to_send = {
        "doc": document["_id"],
        # "meta": {
        #     "source": source,
        #     "ts": _genTimeStamp(),
        #     "user_id": self.used_id
        # },
        "op": ops_buffer,
        "v": document["version"],
        "lastV": document["version"] - 1,
        "hash":
            content_hash  # overleaf/web: sends document hash (if it hasn't been sent in the last 5 seconds)
    }

    if track:
      obj_to_send['meta'] = {'tc': generateId()}

    # notify server of local change
    self.log.debug(
        "Sending %i changes to document %s (ver %i)." %
        (len(ops_buffer), document["_id"], document["version"]))
    await self.send(
        "cmd", {
            "name": "applyOtUpdate",
            "args": [document["_id"], obj_to_send]
        },
        event=event)
    self.log.debug(f"Sent {document['_id']}.")

    # server needs to answer before proceeding
    if self.wait_for is None:
      await event.wait
    else:
      try:
        await wait_for(event.wait(), timeout=self.wait_for)
      except TimeoutError:
        await self.disconnect(
            "Error: The server did not answer for %d seconds." % self.wait_for)
    await self.gui_await(False)
    self.log.debug(
        " -> Waiting for server to accept changes to document %s (ver %i)-> done"
        % (document["_id"], document["version"]))

  # sendOps whenever events appear in queue
  # (is only called in constructor)
  async def sendOps_flush(self):
    async def dequeue(all_ops):
      document, content_hash, ops, track, close = await self.ops_queue.get()
      if close:
        return close, ()
      self.log.debug(f"Got Op {document, content_hash, ops}")
      if document["_id"] not in all_ops:
        all_ops[document["_id"]] = ops
      else:
        all_ops[document["_id"]] += ops
      return close, (document, content_hash, ops, track)

    self.log.debug("Starting Queue")
    try:
      # collects ops and sends them in a batch, server is ready
      while self.project.get("connected"):
        all_ops = {}
        # await first element
        close, payload = await dequeue(all_ops)
        if close:
          return
        # get also all other elements that are currently in queue
        num = self.ops_queue.qsize()
        for i in range(num):
          close, payload = await dequeue(all_ops)
          if close:
            return

        # apply all ops one after another
        for doc_id, ops in all_ops.items():
          document = self.documents[doc_id]
          await self._sendOps(*payload)
    except Exception as e:
      await self.sidebarMsg("Error: " + type(e).__name__ + ": " + str(e))
      await self.disconnect(
          f"Op Failed: {e}")
      raise
    self.log.debug("Queue Exited")

  async def joinDocument(self, buffer):

    # register buffer in document
    doc = buffer.document
    doc["buffer"] = buffer

    # register document in project_handler
    self.documents[doc["_id"]] = doc

    # register document op-buffer
    self.documents[doc["_id"]]["ops_buffer"] = []

    # register for document-watching
    await self.send(
        "cmd", {
            "name": "joinDoc",
            "args": [doc["_id"], {
                "encodeRanges": True
            }]
        })

  async def disconnect(self, msg="Disconnected."):
    await self.connection_lock.acquire()
    # Cleanup and inform threads
    self.log.debug("Connection Closed. Reason:" + msg)
    self.project["msg"] = msg
    self.project["open"] = False
    self.project["connected"] = False
    self.heartbeat.stop()
    if "await" in self.project:
      del self.project["await"]
    if self.ws and self.ws.close_code is None:
      self.ws.close()
    await self.ops_queue.put((None, None, None, None, True))
    doc = None
    for doc in self.documents.values():
      create_task(doc["buffer"].deactivate())
    if msg == "Disconnected.":
      if doc and len(doc["buffer"].allBuffers) > 0:
        create_task(self.sidebar.updateStatus("Connected"))
      else:
        create_task(self.sidebar.updateStatus("Online"))
    self.connection_lock.release()
    await self.sidebar.triggerRefresh()

  async def connect(self):
    try:
      await self.connection_lock.acquire()
      await self.sidebarMsg("Connecting Websocket.")
      self.project["connected"] = True
      # start tornado event loop & related callbacks
      IOLoop.current().spawn_callback(self.sendOps_flush)
      self.heartbeat.start()

      self.log.debug("Initializing websocket connection to " + self.url)
      if "GCLB=" not in self.cookie:
        request = HTTPRequest(
            self.url,
            headers={'Cookie': self.cookie},
            validate_cert=self.validate_cert)
        self.ws = await websocket_connect(request)
        # Should set the GCLB value
        for set_cookie_header in self.ws.headers.get_list('Set-Cookie'):
          cookie = SimpleCookie(set_cookie_header)
          for key, morsel in cookie.items():
            self.session.httpHandler.cookies.set(key, morsel.value)
        self.cookie = self.session.cookies,
      request = HTTPRequest(
          self.url,
          headers={'Cookie': self.cookie},
          validate_cert=self.validate_cert)
      self.ws = await websocket_connect(request)

    except Exception as e:
      self.connection_lock.release()
      await self.disconnect(f"Connection Error: {str(e)}")
    else:
      self.connection_lock.release()
      await self.sidebarMsg("Connected.")
      await self.run()

  async def run(self):
    try:
      self.comments = await self.getComments()
      self.log.debug("Starting WS loop")
      # Should always be connected, because this is spawned by run
      # Which sets connected.
      while self.project.get("connected"):
        msg = await self.ws.read_message()

        if msg is None:
          break
        self.log.debug("Raw server answer: " + msg)

        # parse the code
        code, await_id, await_mult, answer_id, answer_mult, data = codere.match(
            msg).groups()
        if data:
          try:
            data = json.loads(data)
          except:
            data = {"name": "error"}

        # error occured
        if code == "0":
          await self.disconnect("Error: The server closed the connection.")

        # first message
        elif code == "1":
          await self.gui_await(False)

        # keep alive
        elif code == "2":
          self.keep_alive()

        # server request
        elif code == "5":
          if not isinstance(data, dict):
            pass

          # connection accepted => join Project
          if data["name"] == "connectionAccepted":
            _, self.session_id = data["args"]
            await self.sidebarMsg("Connection Active.")
            await self.send(
                "cmd", {
                    "name": "joinProject",
                    "args": [{
                        "project_id": self.project["id"]
                    }]
                })

          # broadcastDocMeta => we ignore it at first
          elif data["name"] == "broadcastDocMeta":
            pass

          # client Connected => delete from cursor list
          elif data["name"] == "clientTracking.clientUpdated":
            for cursor in data["args"]:
              if "id" in cursor and cursor["id"] in self.cursors:
                self.cursors[cursor["id"]].update(cursor)
            await self.updateRemoteCursor(data["args"])

          # client Disconnected => delete from cursor list
          elif data["name"] == "clientTracking.clientDisconnected":
            for id in data["args"]:
              if id in self.cursors:
                del self.cursors[id]
            await self.clearRemoteCursor(*data["args"])

          # update applied => apply update to buffer
          elif data["name"] == "otUpdateApplied":

            # nothing to do?
            if "args" not in data:
              continue

            # apply update to buffer
            for op in data["args"]:
              await self.bufferDo(op["doc"], "applyUpdate", op)

          # error occured
          elif data["name"] == "otUpdateError":
            await self.disconnect(
                "Error occured on operation Update: " + data["args"][0])

          # Bit of a hack, but trying to keep state consistent might
          # be very annoying
          elif data["name"] in ("resolve-thread", "new-comment", "edit-message",
                                "delete-message", "reopen-thread"):
            if data["name"] == "new-comment":
              thread = data["args"][0]
              if thread in self.pending_comments:
                doc_id, count, content = self.pending_comments[thread]
                self.documents[doc_id]["buffer"].publishComment(
                    thread, count, content)
                continue

            self.comments = await self.getComments()
            thread_id = data["args"][0]
            for doc in self.documents.values():
              docbuf = doc["buffer"]
              if thread_id in docbuf.threads:
                if data["name"] in ("resolve-thread", "reopen-thread"):
                  docbuf.threads[thread_id]["resolved"] = (
                      "resolve-thread" == data["name"])
                await docbuf.highlightComments(self.comments)
            create_task(self.session.comments.triggerRefresh())

          # unknown message
          else:
            await self.sidebarMsg("Data not known: " + msg)

        # answer to our request
        elif code == "6":

          # get request command
          request = self.requests[answer_id]
          cmd = request["name"]

          # joinProject => server lists project information
          if cmd == "joinProject":
            project_info = data[1]
            if self.log.level == DEBUG:
              self.log.debug(json.dumps(project_info))
            self.project.update(project_info)
            self.project["open"] = True
            await self.send("cmd", {"name": "clientTracking.getConnectedUsers"})
            await self.sidebar.triggerRefresh()

          elif cmd == "joinDoc":
            id = request["args"][0]
            await self.bufferDo(
                id, "write",
                [d.encode("latin1").decode("utf8") for d in data[1]])
            self.documents[id]["version"] = data[2]
            # Unknown #3
            await self.bufferDo(
                id, "highlightComments", data[4].get("comments", []))
            # self.change_meta = data[4].get("changes", [])

          elif cmd == "applyOtUpdate":
            id = request["args"][0]

            # version increase should be before next event
            self.documents[id]["version"] += 1

            # flush next
            request["event"].set()

            # remove awaiting request
            del self.requests[answer_id]
            # If this was confirmation on sending a comment, then we
            # want to cleanup
            contains_comments = False
            for op in request["args"][1]["op"]:
              # It's a comment!
              if 'c' in op:
                del self.pending_comments[op['t']]
                self.documents[id]["buffer"].threads[op['t']] = {
                    "id": op['t'],
                    "op": op
                }
                contains_comments = True
            if contains_comments:
              self.comments = await self.getComments()
              await self.documents[id]["buffer"].highlightComments(
                  self.comments)
              await self.session.comments.triggerRefresh()

          elif cmd == "clientTracking.getConnectedUsers":
            for cursor in data[1]:
              if "cursorData" in cursor:
                cursorData = cursor["cursorData"]
                del cursor["cursorData"]
                cursor.update(cursorData)
              self.cursors[cursor["client_id"]] = cursor
            await self.updateRemoteCursor(data[1])

          elif cmd == "clientTracking.updatePosition":
            # server accepted the change
            del self.requests[answer_id]
          else:
            await self.sidebarMsg(f"Data not known {cmd}:" + str(msg))

        # answer to our request
        elif code == "7":
          await self.sidebarMsg(
              "Error: Unauthorized. My guess is that"
              " your session cookies are outdated or"
              " not loaded. Typically reloading"
              " '%s/project' using the browser you"
              " used for login should reload the"
              " cookies." % self.session.url)

        # unknown message
        else:
          await self.sidebarMsg("Unknown Code:" + str(msg))
    except (gen.Return, StopIteration):
      raise
    except Exception as e:
      await self.sidebarMsg("Error: " + type(e).__name__ + ": " + str(e))
      await self.disconnect(
          f"WS loop Failed: {e}")
      raise
    self.log.debug("WS Exited")

  async def keep_alive(self):
    await self.send("keep_alive")
