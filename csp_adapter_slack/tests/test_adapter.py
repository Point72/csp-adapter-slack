from datetime import timedelta
from ssl import create_default_context
from unittest.mock import MagicMock, call, patch

import csp
import pytest
from csp import ts
from pydantic import ValidationError

from csp_adapter_slack import SlackAdapterConfig, SlackAdapterManager, SlackMessage, mention_user


@csp.node
def hello(msg: ts[SlackMessage]) -> ts[SlackMessage]:
    if csp.ticked(msg):
        text = f"Hello <@{msg.user_id}>!"
        return SlackMessage(
            channel="a new channel",
            # reply in thread
            thread=msg.thread,
            msg=text,
        )


@csp.node
def react(msg: ts[SlackMessage]) -> ts[SlackMessage]:
    if csp.ticked(msg):
        return SlackMessage(
            channel=msg.channel,
            channel_id=msg.channel_id,
            thread=msg.thread,
            reaction="eyes",
        )


@csp.node
def send_fake_message(clientmock: MagicMock, requestmock: MagicMock, am: SlackAdapterManager) -> ts[bool]:
    with csp.alarms():
        a_send = csp.alarm(bool)
    with csp.start():
        csp.schedule_alarm(a_send, timedelta(seconds=1), True)
    if csp.ticked(a_send):
        if a_send:
            am._process_slack_message(clientmock, requestmock)
            csp.schedule_alarm(a_send, timedelta(seconds=1), False)
        else:
            return True


# Payload from slack-sdk mock: app_mention in public channel
PUBLIC_CHANNEL_MENTION_PAYLOAD = {
    "token": "ABCD",
    "team_id": "EFGH",
    "api_app_id": "HIJK",
    "event": {
        "client_msg_id": "1234-5678",
        "type": "app_mention",
        "text": "<@BOTID> <@USERID> <@USERID2>",
        "user": "USERID",
        "ts": "1.2",
        "blocks": [
            {
                "type": "rich_text",
                "block_id": "tx381",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {"type": "user", "user_id": "BOTID"},
                            {"type": "text", "text": " "},
                            {"type": "user", "user_id": "USERID"},
                            {"type": "text", "text": " "},
                            {"type": "user", "user_id": "USERID2"},
                        ],
                    }
                ],
            }
        ],
        "team": "ABCD",
        "channel": "EFGH",
        "event_ts": "1.2",
    },
    "type": "event_callback",
    "event_id": "ABCD",
    "event_time": 1707423091,
    "authorizations": [{"enterprise_id": None, "team_id": "ABCD", "user_id": "BOTID", "is_bot": True, "is_enterprise_install": False}],
    "is_ext_shared_channel": False,
    "event_context": "SOMELONGCONTEXT",
}
DIRECT_MESSAGE_PAYLOAD = {
    "token": "ABCD",
    "team_id": "EFGH",
    "context_team_id": "ABCD",
    "context_enterprise_id": None,
    "api_app_id": "HIJK",
    "event": {
        "client_msg_id": "1234-5678",
        "type": "message",
        "text": "test",
        "user": "USERID",
        "ts": "2.1",
        "blocks": [
            {
                "type": "rich_text",
                "block_id": "gB9fq",
                "elements": [{"type": "rich_text_section", "elements": [{"type": "text", "text": "test"}]}],
            }
        ],
        "team": "ABCD",
        "channel": "EFGH",
        "event_ts": "2.1",
        "channel_type": "im",
    },
    "type": "event_callback",
    "event_id": "ABCD",
    "event_time": 1707423220,
    "authorizations": [{"enterprise_id": None, "team_id": "ABCD", "user_id": "BOTID", "is_bot": True, "is_enterprise_install": False}],
    "is_ext_shared_channel": False,
    "event_context": "SOMELONGCONTEXT",
}

# Payload from slack-sdk mock: message in public channel (with empty blocks)
PUBLIC_CHANNEL_MESSAGE_EMPTY_BLOCKS_PAYLOAD = {
    "token": "verification-token",
    "team_id": "T111",
    "api_app_id": "A111",
    "event": {
        "client_msg_id": "f0582a78-72db-4feb-b2f3-1e47d66365c8",
        "type": "message",
        "text": "<@U111> Hi here!",
        "user": "U222",
        "ts": "1610241741.000200",
        "team": "T111",
        "channel": "C111",
        "event_ts": "1610241741.000200",
        "channel_type": "channel",
        "blocks": [],
    },
    "type": "event_callback",
    "event_id": "Ev111",
    "event_time": 1610241741,
    "authorizations": [{"enterprise_id": None, "team_id": "T111", "user_id": "U333", "is_bot": True, "is_enterprise_install": False}],
    "is_ext_shared_channel": False,
    "event_context": "1-message-T111-C111",
}

# Payload: message with subtype (should be ignored)
MESSAGE_WITH_SUBTYPE_PAYLOAD = {
    "token": "ABCD",
    "team_id": "EFGH",
    "api_app_id": "HIJK",
    "event": {
        "type": "message",
        "subtype": "channel_join",
        "text": "User joined the channel",
        "user": "USERID",
        "ts": "3.0",
        "channel": "EFGH",
        "event_ts": "3.0",
    },
    "type": "event_callback",
    "event_id": "ABCD2",
    "event_time": 1707423091,
    "authorizations": [{"enterprise_id": None, "team_id": "ABCD", "user_id": "BOTID", "is_bot": True, "is_enterprise_install": False}],
    "is_ext_shared_channel": False,
    "event_context": "SOMELONGCONTEXT",
}

# Payload: IM message (direct message)
IM_MESSAGE_PAYLOAD = {
    "token": "ABCD",
    "team_id": "EFGH",
    "api_app_id": "HIJK",
    "event": {
        "client_msg_id": "im-1234",
        "type": "message",
        "text": "Hello in DM",
        "user": "USERID",
        "ts": "4.0",
        "team": "ABCD",
        "channel": "DM_CHANNEL",
        "event_ts": "4.0",
        "channel_type": "im",
        "blocks": [],
    },
    "type": "event_callback",
    "event_id": "IM_EVENT",
    "event_time": 1707423220,
    "authorizations": [{"enterprise_id": None, "team_id": "ABCD", "user_id": "BOTID", "is_bot": True, "is_enterprise_install": False}],
    "is_ext_shared_channel": False,
    "event_context": "SOMELONGCONTEXT",
}

# Payload from slack-sdk: slash command (non-events_api type)
SLASH_COMMAND_PAYLOAD = {
    "token": "verification-token",
    "team_id": "T111",
    "team_domain": "xxx",
    "channel_id": "C111",
    "channel_name": "random",
    "user_id": "U111",
    "user_name": "testxyz",
    "command": "/hello-socket-mode",
    "text": "",
    "api_app_id": "A111",
    "response_url": "https://hooks.slack.com/commands/T111/111/xxx",
    "trigger_id": "111.222.xxx",
}

# Payload with nested elements for tag extraction
MESSAGE_WITH_NESTED_TAGS_PAYLOAD = {
    "token": "ABCD",
    "team_id": "EFGH",
    "api_app_id": "HIJK",
    "event": {
        "client_msg_id": "nested-tags-1234",
        "type": "message",
        "text": "Hello <@USER1> and <@USER2>!",
        "user": "USERID",
        "ts": "5.0",
        "team": "ABCD",
        "channel": "EFGH",
        "event_ts": "5.0",
        "blocks": [
            {
                "type": "rich_text",
                "block_id": "blk1",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {"type": "text", "text": "Hello "},
                            {"type": "user", "user_id": "USER1"},
                            {"type": "text", "text": " and "},
                            {"type": "user", "user_id": "USER2"},
                            {"type": "text", "text": "!"},
                        ],
                    },
                    {
                        "type": "rich_text_quote",
                        "elements": [
                            {"type": "user", "user_id": "USER3"},
                        ],
                    },
                ],
            }
        ],
    },
    "type": "event_callback",
    "event_id": "NESTED_EVENT",
    "event_time": 1707423300,
    "authorizations": [{"enterprise_id": None, "team_id": "ABCD", "user_id": "BOTID", "is_bot": True, "is_enterprise_install": False}],
    "is_ext_shared_channel": False,
    "event_context": "SOMELONGCONTEXT",
}


class TestSlack:
    def test_slack_tokens(self):
        with pytest.raises(ValidationError):
            SlackAdapterConfig(app_token="abc", bot_token="xoxb-def")
        with pytest.raises(ValidationError):
            SlackAdapterConfig(app_token="xapp-abc", bot_token="def")

    @pytest.mark.parametrize("payload", (PUBLIC_CHANNEL_MENTION_PAYLOAD, DIRECT_MESSAGE_PAYLOAD))
    def test_slack(self, payload):
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            # mock out the event from the slack sdk
            reqmock = MagicMock()
            reqmock.type = "events_api"
            reqmock.payload = payload

            # mock out the user/channel lookup responses
            mock_user_response = MagicMock(name="users_info_mock")
            mock_user_response.status_code = 200
            mock_user_response.data = {"user": {"profile": {"real_name_normalized": "johndoe", "email": "johndoe@some.email"}, "name": "blerg"}}
            clientmock.return_value.web_client.users_info.return_value = mock_user_response
            mock_channel_response = MagicMock(name="conversations_info_mock")
            mock_channel_response.status_code = 200
            mock_channel_response.data = {"channel": {"is_im": False, "is_private": True, "name": "a private channel"}}
            clientmock.return_value.web_client.conversations_info.return_value = mock_channel_response
            mock_list_response = MagicMock(name="conversations_list_mock")
            mock_list_response.status_code = 200
            mock_list_response.data = {
                "channels": [
                    {"name": "a private channel", "id": "EFGH"},
                    {"name": "a new channel", "id": "new_channel"},
                ]
            }
            clientmock.return_value.web_client.conversations_list.return_value = mock_list_response

            def graph():
                am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

                # send a fake slack message to the app
                stop = send_fake_message(clientmock, reqmock, am)

                # send a response
                resp = hello(csp.unroll(am.subscribe()))
                am.publish(resp)

                # do a react
                rct = react(csp.unroll(am.subscribe()))
                am.publish(rct)

                csp.add_graph_output("response", resp)
                csp.add_graph_output("react", rct)

                # stop after first messages
                done_flag = (csp.count(stop) + csp.count(resp) + csp.count(rct)) == 3
                csp.stop_engine(done_flag)

            # run the graph
            resp = csp.run(graph, realtime=True)

            # check outputs
            if payload == PUBLIC_CHANNEL_MENTION_PAYLOAD:
                assert resp["react"]
                assert resp["response"]

                assert resp["react"][0][1] == SlackMessage(channel="a private channel", channel_id="EFGH", reaction="eyes", thread="1.2")
                assert resp["response"][0][1] == SlackMessage(channel="a new channel", msg="Hello <@USERID>!", thread="1.2")
            else:
                assert resp["react"]
                assert resp["response"]

                assert resp["react"][0][1] == SlackMessage(channel="a private channel", channel_id="EFGH", reaction="eyes", thread="2.1")
                assert resp["response"][0][1] == SlackMessage(channel="a new channel", msg="Hello <@USERID>!", thread="2.1")

            # check all inbound mocks got called
            if payload == PUBLIC_CHANNEL_MENTION_PAYLOAD:
                assert clientmock.return_value.web_client.users_info.call_count == 3
            else:
                assert clientmock.return_value.web_client.users_info.call_count == 1
            assert clientmock.return_value.web_client.conversations_info.call_count == 1

            # check all outbound mocks got called
            assert clientmock.return_value.web_client.reactions_add.call_count == 1
            assert clientmock.return_value.web_client.chat_postMessage.call_count == 1

            if payload == PUBLIC_CHANNEL_MENTION_PAYLOAD:
                assert clientmock.return_value.web_client.reactions_add.call_args_list == [call(channel="EFGH", name="eyes", timestamp="1.2")]
                assert clientmock.return_value.web_client.chat_postMessage.call_args_list == [call(channel="new_channel", text="Hello <@USERID>!")]
            else:
                assert clientmock.return_value.web_client.reactions_add.call_args_list == [call(channel="EFGH", name="eyes", timestamp="2.1")]
                assert clientmock.return_value.web_client.chat_postMessage.call_args_list == [call(channel="new_channel", text="Hello <@USERID>!")]

    def test_mention_user(self):
        assert mention_user("ABCD") == "<@ABCD>"

    def test_channel_data_to_channel_kind(self):
        """Test _channel_data_to_channel_kind for different channel types."""
        with patch("csp_adapter_slack.adapter.SocketModeClient"):
            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            # Test IM channel
            assert am._channel_data_to_channel_kind({"is_im": True}) == "message"

            # Test private channel
            assert am._channel_data_to_channel_kind({"is_im": False, "is_private": True}) == "private"

            # Test public channel
            assert am._channel_data_to_channel_kind({"is_im": False, "is_private": False}) == "public"

            # Test missing keys (defaults)
            assert am._channel_data_to_channel_kind({}) == "public"

    def test_get_tags_from_message_empty(self):
        """Test _get_tags_from_message with empty blocks."""
        with patch("csp_adapter_slack.adapter.SocketModeClient"):
            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))
            tags = am._get_tags_from_message([])
            assert tags == []

    def test_get_tags_from_message_nested(self):
        """Test _get_tags_from_message with nested blocks containing user mentions."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            # Mock user lookup
            mock_user_response = MagicMock()
            mock_user_response.status_code = 200
            mock_user_response.data = {"user": {"profile": {"real_name_normalized": "John Doe"}, "name": "johndoe"}}
            clientmock.return_value.web_client.users_info.return_value = mock_user_response

            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            blocks = [
                {
                    "type": "rich_text",
                    "elements": [
                        {
                            "type": "rich_text_section",
                            "elements": [
                                {"type": "user", "user_id": "U123"},
                                {"type": "text", "text": " hello "},
                                {"type": "user", "user_id": "U456"},
                            ],
                        }
                    ],
                }
            ]
            tags = am._get_tags_from_message(blocks)
            # Should find both users
            assert len(tags) == 2
            assert "John Doe" in tags

    def test_message_with_subtype_ignored(self):
        """Test that messages with subtypes are ignored."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            reqmock = MagicMock()
            reqmock.type = "events_api"
            reqmock.payload = MESSAGE_WITH_SUBTYPE_PAYLOAD

            # Process the message
            am._process_slack_message(clientmock, reqmock)

            # Queue should be empty since subtype messages are ignored
            assert am._inqueue.empty()

    def test_non_events_api_type_ignored(self):
        """Test that non-events_api types are handled correctly (slash commands, interactive, etc.)."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            reqmock = MagicMock()
            reqmock.type = "slash_commands"
            reqmock.payload = SLASH_COMMAND_PAYLOAD

            # Process the request - should not add to queue
            am._process_slack_message(clientmock, reqmock)

            # Queue should be empty
            assert am._inqueue.empty()

    def test_duplicate_message_deduplication(self):
        """Test that duplicate messages are deduplicated using _seen_msg_ids."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            mock_user_response = MagicMock()
            mock_user_response.status_code = 200
            mock_user_response.data = {"user": {"profile": {"real_name_normalized": "johndoe"}, "name": "johndoe"}}
            clientmock.return_value.web_client.users_info.return_value = mock_user_response

            mock_channel_response = MagicMock()
            mock_channel_response.status_code = 200
            mock_channel_response.data = {"channel": {"is_im": False, "is_private": False, "name": "general"}}
            clientmock.return_value.web_client.conversations_info.return_value = mock_channel_response

            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            reqmock = MagicMock()
            reqmock.type = "events_api"
            reqmock.payload = DIRECT_MESSAGE_PAYLOAD

            # Process the message twice
            am._process_slack_message(clientmock, reqmock)
            am._process_slack_message(clientmock, reqmock)

            # Only one message should be in the queue (second one should be deduped)
            assert am._inqueue.qsize() == 1

    def test_get_user_from_name(self):
        """Test _get_user_from_name for user lookup by name."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            mock_users_list_response = MagicMock()
            mock_users_list_response.status_code = 200
            mock_users_list_response.data = {
                "members": [
                    {"id": "U123", "name": "john", "profile": {"real_name_normalized": "John Doe", "email": "john@example.com"}},
                    {"id": "U456", "name": "jane", "profile": {"real_name_normalized": "Jane Doe", "email": "jane@example.com"}},
                ]
            }
            clientmock.return_value.web_client.users_list.return_value = mock_users_list_response

            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            # Test user lookup
            user_id = am._get_user_from_name("John Doe")
            assert user_id == "U123"

            # Test cached lookup (should not call API again)
            user_id_cached = am._get_user_from_name("Jane Doe")
            assert user_id_cached == "U456"
            # Only one API call should have been made (both users loaded in first call)
            assert clientmock.return_value.web_client.users_list.call_count == 1

    def test_get_user_from_name_not_found(self):
        """Test _get_user_from_name raises error when user not found."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            mock_users_list_response = MagicMock()
            mock_users_list_response.status_code = 200
            mock_users_list_response.data = {"members": []}
            clientmock.return_value.web_client.users_list.return_value = mock_users_list_response

            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            with pytest.raises(ValueError, match="User .* not found in Slack"):
                am._get_user_from_name("NonExistentUser")

    def test_get_user_from_name_no_email(self):
        """Test _get_user_from_name handles users without email."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            mock_users_list_response = MagicMock()
            mock_users_list_response.status_code = 200
            mock_users_list_response.data = {
                "members": [
                    {"id": "U123", "name": "bot", "profile": {"real_name_normalized": "Bot User"}},
                ]
            }
            clientmock.return_value.web_client.users_list.return_value = mock_users_list_response

            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            # Should use user_id as email fallback
            user_id = am._get_user_from_name("Bot User")
            assert user_id == "U123"
            assert am._user_id_to_user_email["U123"] == "U123"

    def test_get_user_from_name_id_in_profile(self):
        """Test _get_user_from_name handles id in profile instead of top-level."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            mock_users_list_response = MagicMock()
            mock_users_list_response.status_code = 200
            mock_users_list_response.data = {
                "members": [
                    {"name": "profile_id_user", "profile": {"id": "U789", "real_name_normalized": "Profile ID User", "email": "profile@example.com"}},
                ]
            }
            clientmock.return_value.web_client.users_list.return_value = mock_users_list_response

            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            user_id = am._get_user_from_name("Profile ID User")
            assert user_id == "U789"

    def test_get_channel_from_name_tagged_format(self):
        """Test _get_channel_from_name with tagged channel format <#CHANNELID|>."""
        with patch("csp_adapter_slack.adapter.SocketModeClient"):
            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            # Test tagged channel format
            channel_id = am._get_channel_from_name("<#C12345|>")
            assert channel_id == "C12345"

    def test_get_channel_from_name_not_found(self):
        """Test _get_channel_from_name raises error when channel not found."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            mock_conv_list_response = MagicMock()
            mock_conv_list_response.status_code = 200
            mock_conv_list_response.data = {"channels": []}
            clientmock.return_value.web_client.conversations_list.return_value = mock_conv_list_response

            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            with pytest.raises(ValueError, match="Channel .* not found in Slack"):
                am._get_channel_from_name("nonexistent-channel")

    def test_get_channel_from_id_im_channel(self):
        """Test _get_channel_from_id with IM (direct message) channel."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            mock_channel_response = MagicMock()
            mock_channel_response.status_code = 200
            mock_channel_response.data = {"channel": {"is_im": True, "is_private": False, "user": "U123"}}
            clientmock.return_value.web_client.conversations_info.return_value = mock_channel_response

            mock_user_response = MagicMock()
            mock_user_response.status_code = 200
            mock_user_response.data = {"user": {"profile": {"real_name_normalized": "DM User", "email": "dm@example.com"}, "name": "dmuser"}}
            clientmock.return_value.web_client.users_info.return_value = mock_user_response

            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            name, kind = am._get_channel_from_id("DM_CHANNEL_ID")
            assert name == "IM"
            assert kind == "message"
            # User name should be mapped to the channel
            assert am._channel_name_to_channel_id["DM User"] == "DM_CHANNEL_ID"

    def test_im_message_channel_handling(self):
        """Test handling of IM messages with proper channel type detection."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            mock_user_response = MagicMock()
            mock_user_response.status_code = 200
            mock_user_response.data = {"user": {"profile": {"real_name_normalized": "johndoe", "email": "johndoe@email.com"}, "name": "johndoe"}}
            clientmock.return_value.web_client.users_info.return_value = mock_user_response

            mock_channel_response = MagicMock()
            mock_channel_response.status_code = 200
            mock_channel_response.data = {"channel": {"is_im": True, "user": "USERID"}}
            clientmock.return_value.web_client.conversations_info.return_value = mock_channel_response

            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            reqmock = MagicMock()
            reqmock.type = "events_api"
            reqmock.payload = IM_MESSAGE_PAYLOAD

            am._process_slack_message(clientmock, reqmock)

            assert not am._inqueue.empty()
            msg = am._inqueue.get()
            assert msg.channel_type == "message"

    def test_message_with_nested_tags(self):
        """Test extracting tags from nested message blocks."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            mock_user_response = MagicMock()
            mock_user_response.status_code = 200

            # Mock different users for each call
            user_data = {
                "USER1": {"real_name_normalized": "User One", "email": "user1@email.com"},
                "USER2": {"real_name_normalized": "User Two", "email": "user2@email.com"},
                "USER3": {"real_name_normalized": "User Three", "email": "user3@email.com"},
                "USERID": {"real_name_normalized": "Author", "email": "author@email.com"},
            }

            def mock_user_info(user):
                resp = MagicMock()
                resp.status_code = 200
                profile = user_data.get(user, {"real_name_normalized": "Unknown", "email": "unknown@email.com"})
                resp.data = {"user": {"profile": profile, "name": profile["real_name_normalized"].lower()}}
                return resp

            clientmock.return_value.web_client.users_info.side_effect = mock_user_info

            mock_channel_response = MagicMock()
            mock_channel_response.status_code = 200
            mock_channel_response.data = {"channel": {"is_im": False, "is_private": False, "name": "general"}}
            clientmock.return_value.web_client.conversations_info.return_value = mock_channel_response

            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            reqmock = MagicMock()
            reqmock.type = "events_api"
            reqmock.payload = MESSAGE_WITH_NESTED_TAGS_PAYLOAD

            am._process_slack_message(clientmock, reqmock)

            assert not am._inqueue.empty()
            msg = am._inqueue.get()
            # Should have extracted all 3 user tags from nested blocks
            assert len(msg.tags) == 3
            assert "User One" in msg.tags
            assert "User Two" in msg.tags
            assert "User Three" in msg.tags

    def test_message_with_empty_blocks(self):
        """Test handling messages with empty blocks array."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            mock_user_response = MagicMock()
            mock_user_response.status_code = 200
            mock_user_response.data = {"user": {"profile": {"real_name_normalized": "johndoe", "email": "johndoe@email.com"}, "name": "johndoe"}}
            clientmock.return_value.web_client.users_info.return_value = mock_user_response

            mock_channel_response = MagicMock()
            mock_channel_response.status_code = 200
            mock_channel_response.data = {"channel": {"is_im": False, "is_private": False, "name": "general"}}
            clientmock.return_value.web_client.conversations_info.return_value = mock_channel_response

            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            reqmock = MagicMock()
            reqmock.type = "events_api"
            reqmock.payload = PUBLIC_CHANNEL_MESSAGE_EMPTY_BLOCKS_PAYLOAD

            am._process_slack_message(clientmock, reqmock)

            assert not am._inqueue.empty()
            msg = am._inqueue.get()
            assert msg.msg == "<@U111> Hi here!"
            assert msg.tags == []

    def test_register_subscriber(self):
        """Test register_subscriber prevents duplicates."""
        with patch("csp_adapter_slack.adapter.SocketModeClient"):
            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            adapter = MagicMock()
            am.register_subscriber(adapter)
            am.register_subscriber(adapter)  # Add same adapter again

            assert len(am._subscribers) == 1

    def test_register_publisher(self):
        """Test register_publisher prevents duplicates."""
        with patch("csp_adapter_slack.adapter.SocketModeClient"):
            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            adapter = MagicMock()
            am.register_publisher(adapter)
            am.register_publisher(adapter)  # Add same adapter again

            assert len(am._publishers) == 1

    def test_stop_when_not_running(self):
        """Test stop() when adapter is not running does nothing."""
        with patch("csp_adapter_slack.adapter.SocketModeClient"):
            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            # Should not raise an error
            am.stop()
            assert am._running is False

    def test_on_tick(self):
        """Test _on_tick adds message to outqueue."""
        with patch("csp_adapter_slack.adapter.SocketModeClient"):
            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            msg = SlackMessage(channel="test", msg="hello")
            am._on_tick(msg)

            assert not am._outqueue.empty()
            assert am._outqueue.get() == msg

    def test_user_id_cached(self):
        """Test that user lookups are cached properly."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            mock_user_response = MagicMock()
            mock_user_response.status_code = 200
            mock_user_response.data = {"user": {"profile": {"real_name_normalized": "Cached User", "email": "cached@email.com"}, "name": "cached"}}
            clientmock.return_value.web_client.users_info.return_value = mock_user_response

            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            # First call - should hit API
            name1, email1 = am._get_user_from_id("U_CACHED")
            assert name1 == "Cached User"
            assert email1 == "cached@email.com"

            # Second call - should use cache
            name2, email2 = am._get_user_from_id("U_CACHED")
            assert name2 == "Cached User"
            assert email2 == "cached@email.com"

            # API should only be called once
            assert clientmock.return_value.web_client.users_info.call_count == 1

    def test_channel_id_cached(self):
        """Test that channel lookups are cached properly."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            mock_channel_response = MagicMock()
            mock_channel_response.status_code = 200
            mock_channel_response.data = {"channel": {"is_im": False, "is_private": False, "name": "cached-channel"}}
            clientmock.return_value.web_client.conversations_info.return_value = mock_channel_response

            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            # First call - should hit API
            name1, kind1 = am._get_channel_from_id("C_CACHED")
            assert name1 == "cached-channel"
            assert kind1 == "public"

            # Second call - should use cache
            name2, kind2 = am._get_channel_from_id("C_CACHED")
            assert name2 == "cached-channel"
            assert kind2 == "public"

            # API should only be called once
            assert clientmock.return_value.web_client.conversations_info.call_count == 1

    def test_get_user_from_name_no_id_raises_error(self):
        """Test _get_user_from_name raises RuntimeError when user has no id."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            mock_users_list_response = MagicMock()
            mock_users_list_response.status_code = 200
            mock_users_list_response.data = {
                "members": [
                    # User without id in either location
                    {"name": "broken", "profile": {"real_name_normalized": "Broken User", "email": "broken@example.com"}},
                ]
            }
            clientmock.return_value.web_client.users_list.return_value = mock_users_list_response

            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            with pytest.raises(RuntimeError, match="No id found in user profile"):
                am._get_user_from_name("Broken User")

    def test_get_channel_from_name_lookup(self):
        """Test _get_channel_from_name with channel lookup via API."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            mock_conv_list_response = MagicMock()
            mock_conv_list_response.status_code = 200
            mock_conv_list_response.data = {
                "channels": [
                    {"name": "general", "id": "C_GENERAL"},
                    {"name": "random", "id": "C_RANDOM"},
                ]
            }
            clientmock.return_value.web_client.conversations_list.return_value = mock_conv_list_response

            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            channel_id = am._get_channel_from_name("general")
            assert channel_id == "C_GENERAL"

            # Check cached lookup
            channel_id_cached = am._get_channel_from_name("random")
            assert channel_id_cached == "C_RANDOM"

            # API should only be called once (both channels loaded in first call)
            assert clientmock.return_value.web_client.conversations_list.call_count == 1

    def test_get_user_from_id_fallback_to_user_name(self):
        """Test _get_user_from_id falls back to user.name when real_name_normalized is missing."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            mock_user_response = MagicMock()
            mock_user_response.status_code = 200
            mock_user_response.data = {"user": {"profile": {}, "name": "fallback_name"}}
            clientmock.return_value.web_client.users_info.return_value = mock_user_response

            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            name, email = am._get_user_from_id("U_FALLBACK")
            assert name == "fallback_name"
            assert email == ""

    def test_get_user_from_name_fallback_to_user_name(self):
        """Test _get_user_from_name falls back to user.name when real_name_normalized is missing."""
        with patch("csp_adapter_slack.adapter.SocketModeClient") as clientmock:
            mock_users_list_response = MagicMock()
            mock_users_list_response.status_code = 200
            mock_users_list_response.data = {
                "members": [
                    {"id": "U123", "name": "fallback_user", "profile": {"email": "fallback@example.com"}},
                ]
            }
            clientmock.return_value.web_client.users_list.return_value = mock_users_list_response

            am = SlackAdapterManager(SlackAdapterConfig(app_token="xapp-1-dummy", bot_token="xoxb-dummy", ssl=create_default_context()))

            # Should use the user.name as the lookup key since real_name_normalized is missing
            user_id = am._get_user_from_name("fallback_user")
            assert user_id == "U123"
