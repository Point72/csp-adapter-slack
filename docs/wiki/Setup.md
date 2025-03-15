This guide will help you setup a new Slack application.

> [!TIP]
> Find relevant docs with GitHub’s search function, use `repo:Point72/csp-adapter-slack type:wiki <search terms>` to search the documentation Wiki Pages.

# Slack Configuration

Create a Slack app on the [Slack App website](https://api.slack.com/apps).

## Basic Information

Navigate to `Settings->Basic Information` in the newly created app menu.

### App-Level Tokens

Create a new app-level token.
Ensure it has the `connections:write` scope.
The token should start with `xapp-`, copy it securely

### Display Information

Set your apps "App Name".
This is required for the csp chat bot framework.

## Socket Mode

Navigate to `Settings->Socket Mode` in the app menu.
Make sure `Enable Socket Mode` is set.

## Interactivity & Shortcuts

Navigate to `Features->Interactivity & Shortcuts` in the app menu.
Ensure `Interactivity` is set.

## Event Subscriptions

Navigate to `Features->Event Subscriptions` in the app menu.
Ensure `Enable Events` is set.
Under `Subscribe to bot events`, ensure the following events are enabled:

- `app_mention`: Subscribe to only the message events that mention your app or bot
- `message.im`: A message was posted in a direct message channel
- `message.groups`: (Optional) A message was posted to a private channel
- `message.channels`: (Optional) A message was posted to a channel

## OAuth & Permissions

Navigate to `Features->OAuth & Permissions` in the app menu.
Navigate to the `Scopes` panel and ensure the following scopes are added:

- `app_mentions:read`: View messages that directly mention the bot in conversations that the app is in
- `channels:join`: Join public channels in a workspace
- `channels:history`: View messages and other content in public channels that the bot has been added to
- `channels:read`: View basic information about public channels in a workspace
- `chat:write`: Send messages as the bot
- `chat:write.public`: Send messages to channels the bot isn't a member of
- `emoji:read`: View custom emoji in a workspace
- `groups:read`: View basic information about private channels that the bot has been added to
- `groups:history`: View messages and other content in private channels that the bot has been added to
- `im:history`: View messages and other content in direct messages that the bot has been added to
- `im:read`: View basic information about direct messages that the bot has been added to
- `im:write`: Start direct messages with people
- `reactions:read`: View emoji reactions and their associated content in channels and conversations that the bot has been added to
- `reactions:write`: Add and edit emoji reactions
- `users:read`: View people in a workspace
- `users:read.email`: View email addresses of people in a workspace
- `users:write`: Set presence for the bot

Under the `OAuth Tokens` panel, yoyu should see a `Bot User OAuth Token`.
The token should start with `xoxb-`, copy it securely.

# Managing tokens

You should have an `app_token` and a `bot_token` from the above steps.

These can be configured directly on the `SlackAdapterConfig`:

```python
from csp_adapter_slack import SlackAdapterConfig

config = SlackAdapterConfig(app_token="xapp-...", bot_token="xoxb-...")
```

Alternatively, these could be stored in local files and the configuration will read them:

**.gitignore**

```raw
.app_token
.bot_token
```

**.app_token**

```raw
xapp-...
```

**.bot_token**

```raw
xoxb-...
```

```python
from csp_adapter_slack import SlackAdapterConfig

config = SlackAdapterConfig(app_token=".app_token", bot_token=".bot_token")
```

# SSL Configuration

In some environments, you might see SSL errors connecting to Slack.
You can provide a custom SSL context as the `ssl` argument to `SlackAdapterConfig`.

> [!WARNING]
>
> This example disables SSL, and is thus unsafe in general.

```python
from ssl import CERT_NONE, create_default_context
from csp_adapter_slack import SlackAdapterConfig

unsafe_context = create_default_context()
unsafe_context.check_hostname = False
unsafe_context.verify_mode = CERT_NONE

config = SlackAdapterConfig(
  app_token=".app_token",
  bot_token=".bot_token",
  ssl=unsafe_context,
)
```
