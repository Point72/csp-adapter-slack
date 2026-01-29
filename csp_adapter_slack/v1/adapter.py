"""Slack adapter for CSP using chatom.

This module provides a CSP adapter for Slack by wrapping chatom's
SlackBackend. It provides Slack-specific enhancements on top of
the generic chatom CSP layer.
"""

import asyncio
import logging
from typing import Optional, Set

import csp
from chatom.csp import BackendAdapter
from chatom.slack import SlackBackend, SlackConfig, SlackMessage
from chatom.slack.presence import SlackPresenceStatus
from csp import ts

__all__ = (
    "SlackAdapter",
    "SlackPresenceStatus",
)

log = logging.getLogger(__name__)


class SlackAdapter(BackendAdapter):
    """CSP adapter for Slack using chatom's SlackBackend.

    This adapter wraps chatom's SlackBackend and provides a CSP
    interface for reading and writing Slack messages.

    The adapter handles:
    - Message subscription via Socket Mode
    - Message publishing
    - Presence management
    - Channel/user name resolution

    Attributes:
        backend: The underlying SlackBackend.
        config: The SlackConfig used by the backend.

    Example:
        >>> from chatom.slack import SlackConfig
        >>> from csp_adapter_slack import SlackAdapter
        >>>
        >>> config = SlackConfig(
        ...     bot_token="xoxb-your-bot-token",
        ...     app_token="xapp-your-app-token",  # For Socket Mode
        ... )
        >>> adapter = SlackAdapter(config)
        >>>
        >>> @csp.graph
        ... def my_bot():
        ...     messages = adapter.subscribe()
        ...     responses = process_messages(messages)
        ...     adapter.publish(responses)
        >>>
        >>> csp.run(my_bot, starttime=datetime.now(), endtime=timedelta(hours=8))
    """

    def __init__(self, config: SlackConfig):
        """Initialize the Slack adapter.

        Args:
            config: Slack configuration from chatom.
        """
        backend = SlackBackend(config=config)
        super().__init__(backend)
        self._config = config

    @property
    def config(self) -> SlackConfig:
        """Get the Slack configuration."""
        return self._config

    @property
    def slack_backend(self) -> SlackBackend:
        """Get the underlying SlackBackend."""
        return self._backend

    # @csp.graph # NOTE: cannot use decorator, https://github.com/Point72/csp/issues/183
    def subscribe(
        self,
        channels: Optional[Set[str]] = None,
        skip_own: bool = True,
        skip_history: bool = True,
    ) -> ts[[SlackMessage]]:
        """Subscribe to Slack messages.

        Args:
            channels: Optional set of channels to filter. Can be channel IDs
                or channel names; names will be resolved to IDs at connection time.
            skip_own: If True, skip messages from the bot itself.
            skip_history: If True, skip messages before stream started.

        Returns:
            Time series of SlackMessage lists.

        Example:
            >>> @csp.graph
            ... def my_bot():
            ...     # Subscribe to specific channels by name or ID
            ...     messages = adapter.subscribe(channels={"general", "C12345"})
            ...     # Or all channels
            ...     messages = adapter.subscribe()
        """
        return super().subscribe(
            channels=channels,
            skip_own=skip_own,
            skip_history=skip_history,
        )

    # @csp.graph. # NOTE: cannot use decorator, https://github.com/Point72/csp/issues/183
    def publish(self, msg: ts[SlackMessage]):
        """Publish messages to Slack.

        Args:
            msg: Time series of SlackMessages to send.

        Example:
            >>> @csp.graph
            ... def my_bot():
            ...     response = csp.const(SlackMessage(
            ...         channel_id="C12345",
            ...         content="Hello from the bot!",
            ...     ))
            ...     adapter.publish(response)
        """
        # Use the base adapter's publish - it accepts Message which
        # SlackMessage inherits from
        super().publish(msg)

    @csp.node
    def _add_reaction(self, msg: ts[SlackMessage], emoji: ts[str], timeout: float = 5.0):
        """Internal node for adding reactions to messages."""
        if csp.ticked(msg, emoji):
            message = msg
            reaction_emoji = emoji
            config = self._config
            backend_class = type(self._backend)

            def run_reaction():
                async def add_reaction_async():
                    thread_backend = backend_class(config=config)
                    try:
                        await asyncio.wait_for(thread_backend.connect(), timeout=timeout)
                        await asyncio.wait_for(
                            thread_backend.add_reaction(
                                message=message,
                                emoji=reaction_emoji,
                            ),
                            timeout=timeout,
                        )
                    except asyncio.TimeoutError:
                        log.error("Timeout adding reaction")
                    except Exception:
                        log.exception("Failed adding reaction")
                    finally:
                        try:
                            await thread_backend.disconnect()
                        except Exception:
                            pass

                try:
                    asyncio.run(add_reaction_async())
                except Exception:
                    log.exception("Error in reaction thread")

            import threading

            thread = threading.Thread(target=run_reaction, daemon=True)
            thread.start()

    # @csp.graph # NOTE: cannot use decorator, https://github.com/Point72/csp/issues/183
    def publish_reaction(self, msg: ts[SlackMessage], emoji: ts[str], timeout: float = 5.0):
        """Add a reaction to a Slack message.

        Args:
            msg: Time series of SlackMessages to react to.
            emoji: Time series of emoji names (without colons, e.g., "wave", "thumbsup").
            timeout: Timeout for reaction API calls.

        Example:
            >>> @csp.graph
            ... def my_bot():
            ...     messages = adapter.subscribe()
            ...     # React with wave to all messages
            ...     emoji = csp.apply(messages, lambda m: "wave", str)
            ...     adapter.publish_reaction(messages, emoji)
        """
        self._add_reaction(msg=msg, emoji=emoji, timeout=timeout)

    @csp.node
    def _set_slack_presence(self, presence: ts[SlackPresenceStatus], timeout: float = 5.0):
        """Internal node for setting Slack presence.

        Uses a thread with asyncio.run() to avoid event loop conflicts.
        Creates a new backend instance per call to ensure proper async context.
        """
        if csp.ticked(presence):
            status = presence.value  # SlackPresenceStatus is an Enum with string values
            config = self._config
            backend_class = type(self._backend)

            def run_presence():
                async def set_presence_async():
                    # Create new backend for this thread (sessions are loop-bound)
                    thread_backend = backend_class(config=config)
                    try:
                        await asyncio.wait_for(thread_backend.connect(), timeout=timeout)
                        await asyncio.wait_for(thread_backend.set_presence(status), timeout=timeout)
                    except asyncio.TimeoutError:
                        log.error("Timeout setting presence")
                    except Exception:
                        log.exception("Failed setting presence")
                    finally:
                        try:
                            await thread_backend.disconnect()
                        except Exception:
                            pass

                try:
                    asyncio.run(set_presence_async())
                except Exception:
                    log.exception("Error in presence thread")

            import threading

            thread = threading.Thread(target=run_presence, daemon=True)
            thread.start()

    # @csp.graph # NOTE: cannot use decorator, https://github.com/Point72/csp/issues/183
    def publish_presence(self, presence: ts[SlackPresenceStatus], timeout: float = 5.0):
        """Publish presence status updates.

        Note: Setting presence in Slack typically requires a user token (xoxp-),
        not a bot token (xoxb-). This may not work with bot tokens.

        Args:
            presence: Time series of SlackPresenceStatus values.
            timeout: Timeout for presence API calls.

        Example:
            >>> @csp.graph
            ... def my_bot():
            ...     presence = csp.const(SlackPresenceStatus.ACTIVE)
            ...     adapter.publish_presence(presence)
        """
        self._set_slack_presence(presence=presence, timeout=timeout)
