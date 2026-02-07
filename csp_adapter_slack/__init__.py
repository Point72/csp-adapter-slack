"""CSP Adapter for Slack.

This package provides a CSP adapter for Slack by wrapping chatom's
SlackBackend. It provides real-time message streaming and processing
using the csp library.

The adapter uses chatom for all Slack operations:
- Connection management via SlackBackend
- Message models via SlackMessage
- Presence management via SlackPresenceStatus
- Mention formatting utilities
"""

__version__ = "0.4.0"

# Re-export chatom types for convenience
from chatom.slack import SlackBackend, SlackConfig, SlackMessage
from chatom.slack.mention import (
    mention_channel,
    mention_channel_all,
    mention_everyone,
    mention_here,
    mention_user,
    mention_user_group,
)
from chatom.slack.presence import SlackPresenceStatus

# CSP adapter
from .adapter import SlackAdapter

# Alias for backwards compatibility
SlackAdapterConfig = SlackConfig

__all__ = [
    # Adapter
    "SlackAdapter",
    # Config
    "SlackAdapterConfig",  # Legacy
    "SlackConfig",  # chatom config
    # Backend (from chatom)
    "SlackBackend",
    # Message (from chatom)
    "SlackMessage",
    # Presence (from chatom)
    "SlackPresenceStatus",
    # Mentions (from chatom)
    "mention_user",
    "mention_channel",
    "mention_user_group",
    "mention_here",
    "mention_channel_all",
    "mention_everyone",
]
