The below examples are available [in-source](https://github.com/point72/csp-adapter-slack/csp_adapter_slack/examples).
They assume the presence of `.app_token` and `.bot_token` files in the run directory.
Additionally, they assume all optional settings in [Setup](Setup) have been enabled.

# Emoji Wave

Here is a simple example that waves when someone says `hello` in a room or direct message to the bot.
It is available in-source at [`csp_adapter_slack/examples/hello.py`](https://github.com/point72/csp-adapter-slack/csp_adapter_slack/examples/hello.py).

```python
import csp
from csp import ts

from csp_adapter_slack import SlackAdapterConfig, SlackAdapterManager, SlackMessage

config = SlackAdapterConfig(
    app_token=".app_token",
    bot_token=".bot_token",
)


@csp.node
def add_reaction_when_mentioned(msg: ts[SlackMessage]) -> ts[SlackMessage]:
    """Add a reaction to every message to the bot that starts with hello."""
    if "hello" in msg.msg.lower():
        return SlackMessage(
            channel=msg.channel,
            thread=msg.thread,
            reaction="wave",
        )


def graph():
    # Create a DiscordAdapter object
    adapter = SlackAdapterManager(config)

    # Subscribe and unroll the messages
    msgs = csp.unroll(adapter.subscribe())

    # Print it out locally for debugging
    csp.print("msgs", msgs)

    # Add the reaction node
    reactions = add_reaction_when_mentioned(msgs)

    # Print it out locally for debugging
    csp.print("reactions", reactions)

    # Publish the reactions
    adapter.publish(reactions)


if __name__ == "__main__":
    csp.run(graph, realtime=True)
```
