#!/usr/bin/env python
"""Slack CSP End-to-End Integration Test.

This script tests all Slack functionality through the CSP adapter.
Uses CSP for message streaming (subscribe/publish), runs other operations
via async setup before the CSP graph starts.

Environment Variables Required:
    SLACK_BOT_TOKEN: Your Slack bot OAuth token (xoxb-...)
    SLACK_APP_TOKEN: App token for Socket Mode (xapp-...)
    SLACK_TEST_CHANNEL_NAME: Channel where tests run (without #)
    SLACK_TEST_USER_NAME: Username for mention tests (without @)

Usage:
    python -m csp_adapter_slack.tests.integration.slack_csp_e2e
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import List, Optional

import csp
from chatom.base import Channel, Message
from chatom.format import Format, FormattedMessage, Table
from chatom.slack import SlackBackend, SlackConfig, SlackMessage
from chatom.slack.mention import mention_user
from chatom.slack.presence import SlackPresenceStatus
from csp import ts

from csp_adapter_slack import SlackAdapter


def get_env(name: str, required: bool = True) -> Optional[str]:
    """Get environment variable with validation."""
    value = os.environ.get(name)
    if required and not value:
        print(f"❌ Missing required environment variable: {name}")
        sys.exit(1)
    return value


def build_config() -> SlackConfig:
    """Build SlackConfig from environment variables."""
    bot_token = get_env("SLACK_BOT_TOKEN")
    app_token = get_env("SLACK_APP_TOKEN")

    return SlackConfig(
        bot_token=bot_token,
        app_token=app_token,
    )


class TestState:
    """Container for test state."""

    def __init__(self):
        self.results: List[tuple] = []
        self.config: Optional[SlackConfig] = None
        self.channel_id: Optional[str] = None  # Generic field, not backend-specific
        self.user_id: Optional[str] = None
        self.user = None  # Store the user object for mentions
        self.bot_user_id: Optional[str] = None
        self.bot_display_name: Optional[str] = None
        self.received_message: Optional[Message] = None
        self.waiting_for_inbound: bool = False
        self.test_complete: bool = False

    def log(self, message: str, success: bool = True):
        icon = "✅" if success else "❌"
        print(f"{icon} {message}")
        self.results.append((message, success))

    def section(self, title: str):
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}\n")

    def print_summary(self) -> bool:
        self.section("Test Summary")
        passed = sum(1 for _, s in self.results if s)
        failed = sum(1 for _, s in self.results if not s)
        total = len(self.results)
        print(f"  Passed: {passed}/{total}")
        print(f"  Failed: {failed}/{total}")
        if failed > 0:
            print("\n  Failed tests:")
            for msg, success in self.results:
                if not success:
                    print(f"    ❌ {msg}")
        return failed == 0


# Globals
STATE = TestState()
CHANNEL_NAME = get_env("SLACK_TEST_CHANNEL_NAME")
USER_NAME = get_env("SLACK_TEST_USER_NAME")


async def setup_and_run_pre_csp_tests():
    """Run tests that require async operations before CSP starts."""
    STATE.config = build_config()
    backend = SlackBackend(config=STATE.config)

    # Test: Connection
    STATE.section("Test: Connection")
    await backend.connect()
    STATE.log("Connected to Slack successfully")
    print(f"  Backend: {backend.name}")
    print(f"  Format: {backend.format}")

    # Resolve channel
    STATE.section("Resolving Channel")
    channel = await backend.fetch_channel(name=CHANNEL_NAME)
    if channel:
        STATE.channel_id = channel.id
        STATE.log(f"Found channel '#{CHANNEL_NAME}'")
        print(f"  Channel ID: {STATE.channel_id}")
    else:
        STATE.log(f"Channel '#{CHANNEL_NAME}' not found", success=False)
        return False

    # Resolve user
    STATE.section("Resolving User")
    user = await backend.fetch_user(handle=USER_NAME)
    if not user:
        user = await backend.fetch_user(name=USER_NAME)
    if user:
        STATE.user = user  # Store user object for mentions
        STATE.user_id = user.id
        STATE.log(f"Found user '@{user.name}'")
        print(f"  User ID: {STATE.user_id}")
    else:
        STATE.log(f"User '@{USER_NAME}' not found", success=False)
        return False

    # Get bot info
    STATE.section("Getting Bot Info")
    bot_info = await backend.get_bot_info()
    if bot_info:
        STATE.bot_user_id = bot_info.id
        STATE.bot_display_name = bot_info.name
        STATE.log(f"Bot: {bot_info.name} ({bot_info.id})")
    else:
        STATE.log("Could not get bot info", success=False)
        return False

    # Fetch message history (test)
    STATE.section("Test: Fetch Message History")
    try:
        history = await backend.fetch_messages(STATE.channel_id, limit=5)
        STATE.log(f"Fetched {len(history)} messages from history")
        for m in history[:3]:
            preview = (m.content or "")[:40].replace("\n", " ")
            print(f"  - {preview}...")
    except Exception as e:
        STATE.log(f"Fetch message history failed: {e}", success=False)
        print("  (May require groups:history scope for private channels)")

    # Create DM (test)
    STATE.section("Test: Create DM")
    try:
        dm_id = await backend.create_dm([STATE.user_id])
        if dm_id:
            STATE.log(f"Created DM: {dm_id[:20]}...")
            msg = FormattedMessage().add_text("🧪 [CSP E2E] DM test message (async)")
            await backend.send_message(dm_id, msg.render(Format.SLACK_MARKDOWN))
            STATE.log("Sent message to DM")
        else:
            STATE.log("Failed to create DM", success=False)
    except Exception as e:
        STATE.log(f"Create DM failed: {e}", success=False)
        print("  (May require im:write or mpim:write scope)")

    # Disconnect (CSP will create its own connection)
    await backend.disconnect()
    STATE.log("Disconnected (pre-CSP setup complete)")

    return True


@csp.graph
def slack_csp_e2e_graph():
    """CSP graph for message streaming tests."""
    adapter = SlackAdapter(STATE.config)

    # Subscribe to all messages
    messages = adapter.subscribe()

    # Test messages to send
    @csp.node
    def message_sender() -> ts[SlackMessage]:
        """Send test messages via CSP publish."""
        with csp.alarms():
            a_step = csp.alarm(int)

        with csp.start():
            csp.schedule_alarm(a_step, timedelta(milliseconds=500), 0)

        if csp.ticked(a_step):
            step = a_step

            if step == 0:
                # Send plain message
                STATE.section("Test: Send Plain Message (via CSP)")
                timestamp = datetime.now().strftime("%H:%M:%S")
                msg = FormattedMessage().add_text(f"🧪 [CSP E2E] Plain message at {timestamp}")
                STATE.log(f"Sending plain message at {timestamp}")
                csp.schedule_alarm(a_step, timedelta(seconds=1), 1)
                return SlackMessage(channel=Channel(id=STATE.channel_id), content=msg.render(Format.SLACK_MARKDOWN))

            elif step == 1:
                # Send mrkdwn (Slack's markdown)
                STATE.section("Test: Send Mrkdwn Message (via CSP)")
                msg = (
                    FormattedMessage()
                    .add_text("🧪 [CSP E2E] Formatted message:\n")
                    .add_bold("Bold")
                    .add_text(" and ")
                    .add_italic("italic")
                    .add_text("\nCode: ")
                    .add_code("inline_code()")
                )
                STATE.log("Sending mrkdwn message")
                csp.schedule_alarm(a_step, timedelta(seconds=1), 2)
                return SlackMessage(channel=Channel(id=STATE.channel_id), content=msg.render(Format.SLACK_MARKDOWN))

            elif step == 2:
                # Mentions
                STATE.section("Test: Mentions (via CSP)")
                user_mention = mention_user(STATE.user)
                msg = FormattedMessage().add_text("🧪 [CSP E2E] Mention: ").add_raw(user_mention)
                STATE.log("Sending mention message")
                csp.schedule_alarm(a_step, timedelta(seconds=1), 3)
                return SlackMessage(channel=Channel(id=STATE.channel_id), content=msg.render(Format.SLACK_MARKDOWN))

            elif step == 3:
                # Table
                STATE.section("Test: Rich Content Table (via CSP)")
                msg = FormattedMessage().add_text("🧪 [CSP E2E] Table:\n\n")
                table = Table.from_data(
                    headers=["Feature", "Status"],
                    data=[["Subscribe", "✅"], ["Publish", "✅"], ["Mentions", "✅"]],
                )
                msg.content.append(table)
                STATE.log("Sending table message")
                csp.schedule_alarm(a_step, timedelta(seconds=1), 4)
                return SlackMessage(channel=Channel(id=STATE.channel_id), content=msg.render(Format.SLACK_MARKDOWN))

            elif step == 4:
                # Inbound message prompt
                STATE.section("Test: Inbound Messages (via CSP subscribe)")
                msg = (
                    FormattedMessage()
                    .add_text("🧪 ")
                    .add_bold("[CSP E2E] Inbound Message Test")
                    .add_text(f"\n\nPlease @mention the bot: @{STATE.bot_display_name} hello")
                    .add_text("\n\nYou have ")
                    .add_bold("30 seconds")
                    .add_text("...")
                )
                STATE.log("Waiting for inbound message...")
                STATE.waiting_for_inbound = True
                print(f"\n  ⏳ Mention the bot: @{STATE.bot_display_name} hello")
                # Don't schedule next - wait for inbound

                return SlackMessage(channel=Channel(id=STATE.channel_id), content=msg.render(Format.SLACK_MARKDOWN))

            elif step == 5:
                # Confirmation after inbound received
                STATE.section("Test: Inbound Message Received!")
                msg = STATE.received_message
                if msg:
                    STATE.log("Received inbound message via CSP subscribe")
                    print(f"  Message ID: {msg.id}")
                    print(f"  From: {msg.author_id}")
                    preview = (msg.content or "")[:100].replace("\n", " ")
                    print(f"  Content: {preview}...")

                    confirm = (
                        FormattedMessage()
                        .add_text("✅ ")
                        .add_bold("[CSP E2E] Message received via CSP!")
                        .add_text("\n\nYour message was received through adapter.subscribe()")
                    )
                    csp.schedule_alarm(a_step, timedelta(seconds=1), 6)
                    return SlackMessage(channel=Channel(id=STATE.channel_id), content=confirm.render(Format.SLACK_MARKDOWN))
                else:
                    STATE.log("No message received", success=False)
                    csp.schedule_alarm(a_step, timedelta(seconds=1), 6)

            elif step == 6:
                # Done
                STATE.section("CSP Tests Complete")
                STATE.log("All CSP tests finished")
                STATE.test_complete = True
                csp.stop_engine()

    # Inbound message handler - outputs response message when user message received
    @csp.node
    def handle_inbound(msgs: ts[[Message]]) -> ts[SlackMessage]:
        """Handle inbound messages and output response."""
        with csp.state():
            s_found = False

        if csp.ticked(msgs) and STATE.waiting_for_inbound and not s_found:
            result = None
            for msg in msgs:
                # Skip bot's own messages
                if hasattr(msg, "author_id") and msg.author_id == STATE.bot_user_id:
                    continue
                # Got a user message
                STATE.received_message = msg
                STATE.waiting_for_inbound = False
                print(f"\n  📨 Received message: {msg.id}")
                s_found = True

                # Log and build response
                STATE.section("Test: Inbound Message Received!")
                STATE.log("Received inbound message via CSP subscribe")
                print(f"  Message ID: {msg.id}")
                print(f"  From: {msg.author_id}")
                preview = (msg.content or "")[:100].replace("\n", " ")
                print(f"  Content: {preview}...")

                confirm = (
                    FormattedMessage()
                    .add_text("✅ ")
                    .add_bold("[CSP E2E] Message received via CSP!")
                    .add_text("\n\nYour message was received through adapter.subscribe()")
                )
                result = SlackMessage(channel=Channel(id=STATE.channel_id), content=confirm.render(Format.SLACK_MARKDOWN))

                # Mark complete
                STATE.section("CSP Tests Complete")
                STATE.log("All CSP tests finished")
                STATE.test_complete = True
                break

            if result is not None:
                return result

    sender_msgs = message_sender()
    inbound_msgs = handle_inbound(messages)

    # Merge both message streams
    @csp.node
    def merge_messages(m1: ts[SlackMessage], m2: ts[SlackMessage]) -> ts[SlackMessage]:
        if csp.ticked(m1):
            return m1
        if csp.ticked(m2):
            return m2

    outbound = merge_messages(sender_msgs, inbound_msgs)

    # Stop after inbound test complete
    @csp.node
    def check_complete(msgs: ts[SlackMessage]):
        with csp.alarms():
            a_stop = csp.alarm(bool)
        if csp.ticked(msgs) and STATE.test_complete:
            csp.schedule_alarm(a_stop, timedelta(seconds=1), True)
        if csp.ticked(a_stop):
            csp.stop_engine()

    check_complete(inbound_msgs)

    # Publish outbound messages
    adapter.publish(outbound)

    # Presence test (note: may require user token instead of bot token)
    @csp.node
    def presence_sequence() -> ts[SlackPresenceStatus]:
        with csp.alarms():
            a_away = csp.alarm(bool)
            a_auto = csp.alarm(bool)

        with csp.start():
            csp.schedule_alarm(a_away, timedelta(seconds=3), True)
            csp.schedule_alarm(a_auto, timedelta(seconds=5), True)

        if csp.ticked(a_away):
            print("  Setting presence to AWAY")
            STATE.log("Set presence to AWAY")
            return SlackPresenceStatus.AWAY

        if csp.ticked(a_auto):
            print("  Setting presence to AUTO")
            STATE.log("Set presence to AUTO")
            return SlackPresenceStatus.AUTO

    presence = presence_sequence()
    adapter.publish_presence(presence)


async def main_async():
    """Main async entry point."""
    print("\n" + "=" * 60)
    print("  Slack CSP E2E Integration Test")
    print("=" * 60)

    # Phase 1: Async setup tests (fetch channel, user, create DM, etc.)
    print("\n--- Phase 1: Async Setup Tests ---\n")
    if not await setup_and_run_pre_csp_tests():
        return False

    # Phase 2: CSP streaming tests (publish, subscribe, presence)
    print("\n--- Phase 2: CSP Streaming Tests ---\n")
    try:
        csp.run(
            slack_csp_e2e_graph,
            endtime=timedelta(seconds=90),
            realtime=True,
            queue_wait_time=timedelta(milliseconds=100),
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")

    return STATE.print_summary()


def main():
    """Main entry point."""
    success = asyncio.run(main_async())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
