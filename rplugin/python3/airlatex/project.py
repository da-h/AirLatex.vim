from tornado import gen
from tornado.ioloop import IOLoop, PeriodicCallback
from tornado.websocket import websocket_connect
from tornado.httpclient import HTTPRequest
from tornado.locks import Event

import re
import json
from itertools import count

from airlatex.lib.uuid import generateTimeStamp, generateId
from airlatex.buffers.document import Document

from asyncio import Queue, Lock, wait_for, TimeoutError
from logging import getLogger
import traceback

from airlatex.lib.task import AsyncDecorator, Task

from datetime import datetime

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

    # Set thread management here, since refresh clears all of these
    self.connection_lock = Lock()
    self.queue_lock = Lock()
    self.refresh(url, project, csrf, cookie)

    # Default unchanging
    self.session = session

    self.wait_for = wait_for if str(wait_for).isnumeric() else None
    self.validate_cert = validate_cert

    self.log = getLogger("AirLatex")

    self.heartbeat = PeriodicCallback(self.keep_alive, 20000)

  def refresh(self, url, project, csrf, cookie=None):
    self.url = url
    self.data = project
    self.cookie = cookie
    self.csrf = csrf

    # Reset information
    self.command_counter = count(1)
    self.ws = None
    self.session_id = None
    self.requests = {}
    self.cursors = {}
    self.documents = {}
    self.pending_comments = {}

    # Reset thread stuff
    self.ops_queue = Queue()
    self.join_event = Event()
    if self.connection_lock.locked():
      self.connection_lock.release()
    if self.queue_lock.locked():
      self.queue_lock.release()

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
        self.log.debug(f"Sending update: {message_content}")
        self.ws.write_message(f"5:::{message_content}")
      elif message_type == "cmd":
        cmd_id = next(self.command_counter)
        msg = f"5:{cmd_id}+::{message_content}"
        self.log.debug("Sendng cmd: ", msg)
        self.requests[str(cmd_id)] = message
        self.ws.write_message(msg)
    except Exception as e:
      await self.updateSidebar(error=e)
      await self.disconnect(f"Send failed ({type(e).__name__}): {e}")
      raise

  async def updateSidebar(self, msg=None, error=None, waiting=None):
    if error is not None:
      await self.session.sidebar.updateStatus(
          f"Error: {type(error).__name__}: {error}")
    if msg is not None:
      self.data["msg"] = msg
    if waiting is not None:
      self.data["await"] = waiting
    await self.session.sidebar.triggerRefresh()

  async def bufferDo(self, doc_id, command, data):
    # TODO remove bufferDO
    if doc_id in self.documents:
      document = self.documents[doc_id]
      if command == "applyUpdate":
        document.applyUpdate(data, self.comments)
      elif command == "write":
        document.write(data)
      elif command == "updateRemoteCursor":
        document.updateRemoteCursor(data)
      elif command == "clearRemoteCursor":
        document.clearRemoteCursor(data)
      elif command == "highlightComments":
        await document.highlightComments(self.comments, data)

  # wrapper for the ioloop
  async def sendOps(self, document, content_hash, ops=[], track=False):
    await self.ops_queue.put((document, content_hash, ops, track, False))

  # actual sending of ops
  async def _sendOps(self, document, content_hash, ops=[], track=False):

    # append new ops to buffer
    document.data["ops_buffer"] += ops

    # skip if nothing to do
    if len(document.data["ops_buffer"]) == 0:
      return

    # wait if awaiting server response
    event = Event()
    await self.updateSidebar(waiting=True)

    # clean buffer for next call
    ops_buffer, document.data["ops_buffer"] = document.data["ops_buffer"], []

    # actually send operations
    source = document.id

    obj_to_send = {
        "doc": document.id,
        "op": ops_buffer,
        "v": document.version,
        "lastV": document.version - 1,
        "hash":
            content_hash  # overleaf/web: sends document hash (if it hasn't been sent in the last 5 seconds)
    }

    if track:
      obj_to_send['meta'] = {'tc': generateId()}

    # notify server of local change
    self.log.debug(
        f"Sending {len(ops_buffer)} changes to document {document.id}"
        f" (ver {document.version}]).")
    await self.send(
        "cmd", {
            "name": "applyOtUpdate",
            "args": [document.id, obj_to_send]
        },
        event=event)
    self.log.debug(f"Sent {document.id}.")

    # server needs to answer before proceeding
    if self.wait_for is None:
      await event.wait()
    else:
      try:
        await wait_for(event.wait(), timeout=self.wait_for)
      except TimeoutError:
        await self.disconnect(
            f"Error: The server did not answer for {self.wait_for} seconds.")
    await self.updateSidebar(waiting=False)
    self.log.debug(
        f" -> Waiting for server to accept changes to document {document.id}"
        f"(ver {document.version})-> done")

  # sendOps whenever events appear in queue
  # (is only called in constructor)
  async def sendOps_flush(self):

    async def dequeue(all_ops):
      document_id, content_hash, ops, track, close = await self.ops_queue.get()

      if close:
        return close
      self.log.debug(f"Got Op {document_id, content_hash, ops}")
      if document_id not in all_ops:
        all_ops[document_id] = ops
      else:
        all_ops[document_id] += ops
      # The last content hash for the document is the valid one.
      payloads[document_id] = (content_hash, track)
      return close

    self.log.debug("Starting Queue")
    try:
      # collects ops and sends them in a batch, server is ready
      while self.data.get("connected"):
        all_ops = {}
        payloads = {}
        # await first element
        if await dequeue(all_ops):
          return
        # get also all other elements that are currently in queue
        num = self.ops_queue.qsize()
        for i in range(num):
          if await dequeue(all_ops):
            return

        # apply all ops one after another
        for doc_id, ops in all_ops.items():
          document = self.documents[doc_id]
          content_hash, track = payloads[doc_id]
          await self._sendOps(document, content_hash, ops=ops, track=track)
    except Exception as e:
      self.log.debug(traceback.format_exc())
      await self.updateSidebar(error=e)
      await self.disconnect(f"Op Failed: {e}")
      raise e
    self.log.debug("Queue Exited")

  async def joinDocument(self, document):

    # Register a document
    self.documents[document.id] = document

    # register for document-watching
    await self.send(
        "cmd", {
            "name": "joinDoc",
            "args": [document.id, {
                "encodeRanges": True
            }]
        })

  async def disconnect(self, msg="Disconnected."):
    await self.connection_lock.acquire()
    # Cleanup and inform threads
    self.log.debug(f"Connection Closed. Reason: {msg}")
    self.data["msg"] = msg
    self.data["open"] = False
    self.data["connected"] = False
    self.heartbeat.stop()
    if "await" in self.data:
      del self.data["await"]
    if self.ws and self.ws.close_code is None:
      self.ws.close()
    await self.ops_queue.put((None, None, None, None, True))
    doc = None
    for doc in self.documents.values():
      Task(doc.deactivate)
      del doc

    # Intention disconnet
    if msg == "Disconnected.":
      msg = "Online"
      if len(Document.allBuffers) > 0:
        msg = "Connected"

    # A simple reference count shows that this is nowhere ready to be GC'd.
    # So just reuse the object,
    # self.data["handler"] = None
    # self.log.debug(f"References to project {sys.getrefcount(self)}")
    self.connection_lock.release()
    await self.updateSidebar(msg)

  async def connect(self):
    try:
      await self.connection_lock.acquire()
      await self.updateSidebar("Connecting Websocket.")
      self.data["connected"] = True
      # start tornado event loop & related callbacks
      IOLoop.current().spawn_callback(self.sendOps_flush)
      self.heartbeat.start()

      self.log.debug(f"Initializing websocket connection to {self.url}")
      request = HTTPRequest(
          self.url,
          headers={'Cookie': self.cookie},
          validate_cert=self.validate_cert)
      self.ws = await websocket_connect(request)

    except Exception as e:
      self.connection_lock.release()
      self.log.debug(traceback.format_exc())
      await self.disconnect(f"Connection Error: {str(e)}")
    else:
      self.connection_lock.release()
      await self.updateSidebar("Connected.")
      await self.run()

  async def run(self):
    try:
      self.comments = await self.getComments()
      self.log.debug("Starting WS loop")
      # Should always be connected, because this is spawned by run
      # Which sets connected.
      while self.data.get("connected"):
        msg = await self.ws.read_message()

        if msg is None:
          self.log.debug("No msg")
          break
        self.log.debug(f"Raw server answer: {msg}")

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
          await self.updateSidebar(waiting=False)

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
            await self.updateSidebar("Connection Active.")
            await self.send(
                "cmd", {
                    "name": "joinProject",
                    "args": [{
                        "project_id": self.data["id"]
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

            # apply update to buffer
            for op in data.get("args", []):
              await self.bufferDo(op["doc"], "applyUpdate", op)

          # error occured
          elif data["name"] == "otUpdateError":
            await self.disconnect(
                f"Error occured on operation Update: {data['args'][0]}")

          # Bit of a hack, but trying to keep state consistent might
          # be very annoying
          elif data["name"] in ("resolve-thread", "new-comment", "edit-message",
                                "delete-message", "reopen-thread"):
            if self.comments == None:
              Task(self.session.comments.markInvalid())
              continue
            self.log.debug(data)
            if data["name"] == "new-comment":
              thread = data["args"][0]
              if thread in self.pending_comments:
                doc_id, count, content = self.pending_comments[thread]
                Task(
                    self.documents[doc_id].publishComment, thread, count,
                    content).next
                continue

            self.comments = await self.getComments()
            thread_id = data["args"][0]
            for doc in self.documents.values():
              if thread_id in doc.threads.data:
                if data["name"] in ("resolve-thread", "reopen-thread"):
                  doc.threads.data[thread_id]["resolved"] = (
                      "resolve-thread" == data["name"])
                await doc.highlightComments(self.comments)
            Task(self.session.comments.triggerRefresh())

          # unknown message
          else:
            await self.updateSidebar(f"Data not known: {msg}")

        # answer to our request
        elif code == "6":

          # get request command
          request = self.requests[answer_id]
          cmd = request["name"]

          # joinProject => server lists project information
          if cmd == "joinProject":
            project_info = data[1]
            self.log.debug("Joined")
            self.log.debug(json.dumps(project_info))
            self.data.update(project_info)
            self.data["open"] = True
            await self.send("cmd", {"name": "clientTracking.getConnectedUsers"})
            await self.updateSidebar()
            self.join_event.set()

          elif cmd == "joinDoc":
            id = request["args"][0]
            await self.bufferDo(
                id, "write",
                [d.encode("latin1").decode("utf8") for d in data[1]])
            self.documents[id].version = data[2]
            # Unknown #3
            await self.bufferDo(
                id, "highlightComments", data[4].get("comments", []))
            # self.change_meta = data[4].get("changes", [])

          elif cmd == "applyOtUpdate":
            id = request["args"][0]

            # version increase should be before next event
            self.documents[id].version += 1

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
                self.documents[id].threads.data[op['t']] = {"id": op['t'], "op": op}
                contains_comments = True
            if contains_comments:
              self.comments = await self.getComments()
              await self.documents[id].highlightComments(self.comments)
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
            await self.updateSidebar(f"Data not known {cmd}: {msg}")

        # answer to our request
        elif code == "7":
          await self.updateSidebar(
              "Error: Unauthorized. My guess is that"
              " your session cookies are outdated or"
              " not loaded. Typically reloading"
              f" '{self.session.settings.url}/project' using the"
              "browser you used for login should reload the"
              " cookies.")

        # unknown message
        else:
          await self.updateSidebar(f"Unknown Code: {msg}")
    except (gen.Return, StopIteration):
      raise
    except Exception as e:
      self.log.debug(traceback.format_exc())
      await self.updateSidebar(error=e)
      await self.disconnect(f"WS loop Failed: {e}")
      raise
    self.log.debug("WS Exited")

  async def keep_alive(self):
    await self.send("keep_alive")

  @property
  def id(self):
    return self.data["id"]

  # Misc enpoints

  async def syncGit(self, message):
    self.log.debug(f"Syncing. {str(self.data)}")
    # https://www.overleaf.com/project/<project>/github-sync/merge
    compile_url = f"{self.session.settings.url}/project/{self.id}/github-sync/merge"
    response = self.session.httpHandler.post(
        compile_url,
        headers={
            'Cookie': self.cookie,
            'x-csrf-token': self.csrf,
            'content-type': 'application/json'
        },
        json={"message": message})
    try:
      assert response.status_code == 200, f"Bad status code {response.status_code}"
      return True, "Synced."
    except Exception as e:
      self.log.debug(traceback.format_exc())
      self.log.debug("\nError in sync:")
      self.log.debug(f"{response.content}\n---\n{e}")
    return False, "Error, check logs."

  async def compile(self):
    self.log.debug(f"Compiling. {str(self.data)}")
    compile_url = f"{self.session.settings.url}/project/{self.id}/compile?enable_pdf_caching=true"
    response = self.session.httpHandler.post(
        compile_url,
        headers={
            'Cookie': self.cookie,
            'x-csrf-token': self.csrf,
            'content-type': 'application/json'
        },
        json={
            "rootDoc_id": self.data["rootDoc_id"],
            "draft": False,
            "check": "silent",
            "incrementalCompilesEnabled": True,
            "stopOnFirstError": False
        })

    try:
      data = response.json()
      if data["status"] != "success":
        raise Exception("No success in compiling. Something failed.")
      self.log.debug("Compiled.")
    except Exception as e:
      self.log.debug(traceback.format_exc())
      self.log.debug("\nCompilation response content:")
      self.log.debug(f"{response.content}\n---\n{e}")

  async def adjustComment(
      self, thread, state, content="", resolve_state=None, retract=False):
    resolve_url = f"{self.session.settings.url}/project/{self.id}/thread/{thread}/{state}"
    payload = {"_csrf": self.csrf}
    if content:
      payload["content"] = content
    response = self.session.httpHandler.post(
        resolve_url, headers={
            'Cookie': self.cookie,
        }, json=payload)
    self.log.debug(f"adjusting comment to {state}")
    try:
      assert response.status_code == 204, f"Bad status code {response.status_code}"
      # We'll get a websocket confirmation, and handle it from there.
      # Nothing else to do
    except Exception as e:
      self.log.debug(traceback.format_exc())
      self.log.debug("\n {state} response content:")
      self.log.debug(f"{response.content}\n---\n{e}")
      if resolve_state is not None:
        self.comments.get(thread, {})["resolved"] = resolve_state
      if retract:
        del self.comments[thread]

  def resolveComment(self, thread):
    self.comments.get(thread, {})["resolved"] = True
    Task(self.adjustComment(thread, "resolve", resolve_state=False))

  def reopenComment(self, thread):
    self.comments.get(thread, {})["resolved"] = False
    Task(self.adjustComment(thread, "reopen", resolve_state=True))

  def replyComment(self, thread, content):
    self.comments.get(thread, {}).get("messages", []).append(
        {
            "user": {
                "first_name": "** (pending)"
            },
            "content": content,
            "timestamp": datetime.now().timestamp()
        })
    Task(self.adjustComment(thread, "messages", content))

  def createComment(self, thread, doc_id, content):
    doc = self.documents[doc_id]
    interval = doc.threads.selection[:].pop()
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
    Task(self.adjustComment(thread, "messages", content, retract=True))

  async def getComments(self):
    comment_url = f"{self.session.settings.url}/project/{self.id}/threads"
    response = self.session.httpHandler.get(
        comment_url, headers={
            'Cookie': self.cookie,
        })
    try:
      comments = response.json()
      self.log.debug("Got comments")
      return comments
    except Exception as e:
      self.log.debug(traceback.format_exc())
      self.log.debug("\nComments response content:")
      self.log.debug(f"{response.content}\n---\n{e}")
    Task(self.session.comments.markInvalid())
    return None

  async def clearRemoteCursor(self, session_id):
    for document_id in self.documents:
      await self.bufferDo(document_id, "clearRemoteCursor", session_id)

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
