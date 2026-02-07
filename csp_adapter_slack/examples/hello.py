import logging
import os

import csp
from csp import ts

from csp_adapter_slack import SlackAdapter, SlackAdapterConfig, SlackMessage

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

config = SlackAdapterConfig(
    app_token=os.environ.get("SLACK_APP_TOKEN", ""),
    bot_token=os.environ.get("SLACK_BOT_TOKEN", ""),
)


@csp.node
def should_react(msg: ts[SlackMessage]) -> ts[bool]:
    """Return True for messages that contain hello."""
    if csp.ticked(msg):
        return "hello" in msg.text.lower()


def graph():
    # Create a Slack Adapter object
    adapter = SlackAdapter(config)

    # Subscribe and unroll the messages, cast to SlackMessage
    msgs = csp.apply(csp.unroll(adapter.subscribe()), lambda m: m, SlackMessage)

    # Print it out locally for debugging
    csp.print("msgs", msgs)

    # Check if we should react
    react = should_react(msgs)

    # Filter to only messages that should get a reaction
    filtered_msgs = csp.filter(react, msgs)

    # Create emoji stream
    emoji = csp.apply(filtered_msgs, lambda m: "wave", str)

    # Print it out locally for debugging
    csp.print("reacting to", filtered_msgs)

    # Publish the reaction
    adapter.publish_reaction(filtered_msgs, emoji)


if __name__ == "__main__":
    csp.run(graph, realtime=True)
