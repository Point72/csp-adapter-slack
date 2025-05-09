import threading
from logging import getLogger
from queue import Queue
from threading import Thread
from time import sleep
from typing import Dict, List, TypeVar

import csp
from csp.impl.adaptermanager import AdapterManagerImpl
from csp.impl.outputadapter import OutputAdapter
from csp.impl.pushadapter import PushInputAdapter
from csp.impl.types.tstype import ts
from csp.impl.wiring import py_output_adapter_def, py_push_adapter_def
from slack_sdk.errors import SlackApiError
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web import WebClient

from .adapter_config import SlackAdapterConfig
from .message import SlackMessage

T = TypeVar("T")
log = getLogger(__file__)


__all__ = ("SlackAdapterManager", "SlackInputAdapterImpl", "SlackOutputAdapterImpl")


class SlackAdapterManager(AdapterManagerImpl):
    def __init__(self, config: SlackAdapterConfig):
        self._slack_client = SocketModeClient(
            app_token=config.app_token,
            web_client=WebClient(token=config.bot_token, ssl=config.ssl),
        )
        self._slack_client.socket_mode_request_listeners.append(self._process_slack_message)

        # down stream edges
        self._subscribers = []
        self._publishers = []

        # message queues
        self._inqueue: Queue[SlackMessage] = Queue()
        self._outqueue: Queue[SlackMessage] = Queue()

        # handler thread
        self._running: bool = False
        self._thread: Thread = None

        # lookups for mentions and redirection
        self._channel_id_to_channel_name: Dict[str, str] = {}
        self._channel_id_to_channel_type: Dict[str, str] = {}
        self._channel_name_to_channel_id: Dict[str, str] = {}
        self._user_id_to_user_name: Dict[str, str] = {}
        self._user_id_to_user_email: Dict[str, str] = {}
        self._user_name_to_user_id: Dict[str, str] = {}
        self._user_email_to_user_id: Dict[str, str] = {}

        # if subscribed to mentions AND events, will get 2 copies,
        # so we want to dedupe by id
        self._seen_msg_ids = set()

    def subscribe(self):
        return _slack_input_adapter(self, push_mode=csp.PushMode.NON_COLLAPSING)

    def publish(self, msg: ts[SlackMessage]):
        return _slack_output_adapter(self, msg)

    def _create(self, engine, memo):
        # We'll avoid having a second class and make our AdapterManager and AdapterManagerImpl the same
        super().__init__(engine)
        return self

    def start(self, starttime, endtime):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        if self._running:
            self._running = False
            self._slack_client.close()
            self._thread.join()

    def register_subscriber(self, adapter):
        if adapter not in self._subscribers:
            self._subscribers.append(adapter)

    def register_publisher(self, adapter):
        if adapter not in self._publishers:
            self._publishers.append(adapter)

    def _get_user_from_id(self, user_id):
        # try to pull from cache
        name = self._user_id_to_user_name.get(user_id, None)
        email = self._user_id_to_user_email.get(user_id, None)

        # if none, refresh data via web client
        if name is None or email is None:
            ret = self._slack_client.web_client.users_info(user=user_id)
            if ret.status_code == 200:
                # TODO OAuth scopes required
                name = ret.data["user"]["profile"].get("real_name_normalized", ret.data["user"]["name"])
                email = ret.data["user"]["profile"].get("email", "")
                self._user_id_to_user_name[user_id] = name
                self._user_name_to_user_id[name] = user_id  # TODO is this 1-1 in slack?
                self._user_id_to_user_email[user_id] = email
                self._user_email_to_user_id[email] = user_id
        return name, email

    def _get_user_from_name(self, user_name):
        # try to pull from cache
        user_id = self._user_name_to_user_id.get(user_name, None)

        # if none, refresh data via web client
        if user_id is None:
            # unfortunately the reverse lookup is not super nice...
            # we need to pull all users and build the reverse mapping
            ret = self._slack_client.web_client.users_list()
            if ret.status_code == 200:
                # TODO OAuth scopes required
                for user in ret.data["members"]:
                    # Grab name
                    name = user["profile"].get("real_name_normalized", user["name"])

                    # Try to grab id
                    if "id" in user:
                        user_id = user["id"]
                    elif "id" in user["profile"]:
                        user_id = user["profile"]["id"]
                    else:
                        raise RuntimeError(f"No id found in user profile: {user}")

                    # Try to grab email
                    if "email" in user["profile"]:
                        email = user["profile"]["email"]
                    else:
                        log.warning(f"No email found in user profile, using id: {user}")
                        email = user_id

                    self._user_id_to_user_name[user_id] = name
                    self._user_name_to_user_id[name] = user_id  # TODO is this 1-1 in slack?
                    self._user_id_to_user_email[user_id] = email
                    self._user_email_to_user_id[email] = user_id

            user_id = self._user_name_to_user_id.get(user_name, None)
            if user_id is None:
                # no user found
                raise ValueError(f"User {user_name} not found in Slack")
        return user_id

    def _channel_data_to_channel_kind(self, data) -> str:
        if data.get("is_im", False):
            return "message"
        if data.get("is_private", False):
            return "private"
        return "public"

    def _get_channel_from_id(self, channel_id):
        # try to pull from cache
        name = self._channel_id_to_channel_name.get(channel_id, None)
        kind = self._channel_id_to_channel_type.get(channel_id, None)

        # if none, refresh data via web client
        if name is None:
            ret = self._slack_client.web_client.conversations_info(channel=channel_id)
            if ret.status_code == 200:
                # TODO OAuth scopes required
                kind = self._channel_data_to_channel_kind(ret.data["channel"])
                if kind == "message":
                    # TODO use same behavior as symphony adapter
                    name = "IM"
                else:
                    name = ret.data["channel"]["name"]

                if name == "IM":
                    # store by the name of the user
                    user = ret.data["channel"]["user"]
                    user_name = self._get_user_from_id(user)[0]
                    self._channel_name_to_channel_id[user_name] = channel_id
                else:
                    self._channel_name_to_channel_id[name] = channel_id
                self._channel_id_to_channel_name[channel_id] = name
                self._channel_id_to_channel_type[channel_id] = kind
        return name, kind

    def _get_channel_from_name(self, channel_name):
        # first, see if its a regular name or tagged name
        if channel_name.startswith("<#") and channel_name.endswith("|>"):
            # strip out the tag
            channel_id = channel_name[2:-2]
        else:
            # try to pull from cache
            channel_id = self._channel_name_to_channel_id.get(channel_name, None)

        # if none, refresh data via web client
        if channel_id is None:
            # unfortunately the reverse lookup is not super nice...
            # we need to pull all channels and build the reverse mapping
            ret = self._slack_client.web_client.conversations_list()
            if ret.status_code == 200:
                # TODO OAuth scopes required
                for channel in ret.data["channels"]:
                    name = channel["name"]
                    channel_id = channel["id"]
                    kind = self._channel_data_to_channel_kind(channel)
                    self._channel_id_to_channel_name[channel_id] = name
                    self._channel_name_to_channel_id[name] = channel_id
                    self._channel_id_to_channel_type[channel_id] = kind
            channel_id = self._channel_name_to_channel_id.get(channel_name, None)
            if channel_id is None:
                # no channel found
                raise ValueError(f"Channel {channel_name} not found in Slack")
        return channel_id

    def _get_tags_from_message(self, blocks) -> List[str]:
        """extract tags from message, potentially excluding the bot's own @"""
        tags = []
        to_search = blocks.copy()

        while to_search:
            element = to_search.pop()
            # add subsections
            if element.get("elements", []):
                to_search.extend(element.get("elements"))

            if element.get("type", "") == "user":
                tag_id = element.get("user_id")
                name, _ = self._get_user_from_id(tag_id)
                if name:
                    tags.append(name)
        return tags

    def _process_slack_message(self, client: SocketModeClient, req: SocketModeRequest):
        log.info(req.payload)
        if req.type == "events_api":
            # Acknowledge the request anyway
            response = SocketModeResponse(envelope_id=req.envelope_id)
            client.send_socket_mode_response(response)

            if req.payload["event"]["ts"] in self._seen_msg_ids:
                # already seen, pop it and move on
                self._seen_msg_ids.remove(req.payload["event"]["ts"])
                return

            # else add it so we don't process it again
            self._seen_msg_ids.add(req.payload["event"]["ts"])

            if req.payload["event"]["type"] in ("message", "app_mention") and req.payload["event"].get("subtype") is None:
                user, user_email = self._get_user_from_id(req.payload["event"]["user"])
                channel, channel_type = self._get_channel_from_id(req.payload["event"]["channel"])

                tags = self._get_tags_from_message(req.payload["event"]["blocks"])
                slack_msg = SlackMessage(
                    user=user or "",
                    user_email=user_email or "",
                    user_id=req.payload["event"]["user"],
                    tags=tags,
                    channel=channel or "",
                    channel_id=req.payload["event"]["channel"],
                    channel_type=channel_type or "",
                    msg=req.payload["event"]["text"],
                    reaction="",
                    thread=req.payload["event"]["ts"],
                    payload=req.payload.copy(),
                )
                self._inqueue.put(slack_msg)

    def _run(self):
        self._slack_client.connect()

        while self._running:
            # drain outbound
            while not self._outqueue.empty():
                # pull SlackMessage from queue
                slack_msg = self._outqueue.get()

                # refactor into slack command
                # grab channel or DM
                if hasattr(slack_msg, "channel_id") and slack_msg.channel_id:
                    channel_id = slack_msg.channel_id

                elif hasattr(slack_msg, "channel") and slack_msg.channel:
                    channel_id = self._get_channel_from_name(slack_msg.channel)

                # pull text or reaction
                if hasattr(slack_msg, "reaction") and slack_msg.reaction and hasattr(slack_msg, "thread") and slack_msg.thread:
                    # TODO
                    self._slack_client.web_client.reactions_add(
                        channel=channel_id,
                        name=slack_msg.reaction,
                        timestamp=slack_msg.thread,
                    )

                elif hasattr(slack_msg, "msg") and slack_msg.msg:
                    try:
                        # send text to channel
                        self._slack_client.web_client.chat_postMessage(
                            channel=channel_id,
                            text=getattr(slack_msg, "msg", ""),
                        )
                    except SlackApiError:
                        log.exception("Failed to send message to Slack")
                else:
                    # cannot send empty message, log an error
                    log.exception(f"Received malformed SlackMessage instance: {slack_msg}")

            if not self._inqueue.empty():
                # pull all SlackMessages from queue
                # do as burst to match SymphonyAdapter
                slack_msgs = []
                while not self._inqueue.empty():
                    slack_msgs.append(self._inqueue.get())

                # push to all the subscribers
                for adapter in self._subscribers:
                    adapter.push_tick(slack_msgs)

            # do short sleep
            sleep(0.1)

            # liveness check
            if not self._thread.is_alive():
                self._running = False
                self._thread.join()

        # shut down socket client
        try:
            # TODO which one?
            self._slack_client.close()
            # self._slack_client.disconnect()
        except AttributeError:
            # TODO bug in slack sdk causes an exception to be thrown
            #   File "slack_sdk/socket_mode/builtin/connection.py", line 191, in disconnect
            #   self.sock.close()
            #   ^^^^^^^^^^^^^^^
            # AttributeError: 'NoneType' object has no attribute 'close'
            ...

    def _on_tick(self, value):
        self._outqueue.put(value)


class SlackInputAdapterImpl(PushInputAdapter):
    def __init__(self, manager):
        manager.register_subscriber(self)
        super().__init__()


class SlackOutputAdapterImpl(OutputAdapter):
    def __init__(self, manager):
        manager.register_publisher(self)
        self._manager = manager
        super().__init__()

    def on_tick(self, time, value):
        self._manager._on_tick(value)


_slack_input_adapter = py_push_adapter_def(
    name="SlackInputAdapter",
    adapterimpl=SlackInputAdapterImpl,
    out_type=ts[[SlackMessage]],
    manager_type=SlackAdapterManager,
)
_slack_output_adapter = py_output_adapter_def(
    name="SlackOutputAdapter",
    adapterimpl=SlackOutputAdapterImpl,
    manager_type=SlackAdapterManager,
    input=ts[SlackMessage],
)
