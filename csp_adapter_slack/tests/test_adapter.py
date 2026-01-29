"""Tests for the Slack CSP adapter.

This module tests the SlackAdapter that wraps chatom's SlackBackend for CSP.
"""

from unittest.mock import MagicMock, patch

import pytest

# Check for CSP availability
try:
    import csp  # noqa: F401
    from csp import ts  # noqa: F401

    HAS_CSP = True
except ImportError:
    HAS_CSP = False

# Test imports
from csp_adapter_slack import (
    SlackAdapter,
    SlackAdapterConfig,
    SlackConfig,
    SlackMessage,
    mention_channel,
    mention_channel_all,
    mention_everyone,
    mention_here,
    mention_user,
    mention_user_group,
)


class TestSlackConfig:
    """Tests for SlackConfig."""

    def test_slack_config_basic(self):
        """Test basic SlackConfig creation."""
        config = SlackConfig(
            bot_token="xoxb-test-token",
            app_token="xapp-test-token",
        )
        assert config.bot_token_str == "xoxb-test-token"
        assert config.app_token_str == "xapp-test-token"

    def test_slack_config_optional_fields(self):
        """Test SlackConfig with optional fields."""
        config = SlackConfig(
            bot_token="xoxb-test-token",
            default_channel="C12345",
            team_id="T12345",
        )
        assert config.default_channel == "C12345"
        assert config.team_id == "T12345"

    def test_slack_config_has_socket_mode(self):
        """Test has_socket_mode property."""
        config_with_token = SlackConfig(
            bot_token="xoxb-test",
            app_token="xapp-test",
        )
        assert config_with_token.has_socket_mode is True

        config_without_token = SlackConfig(
            bot_token="xoxb-test",
        )
        assert config_without_token.has_socket_mode is False


class TestSlackAdapterConfig:
    """Tests for legacy SlackAdapterConfig."""

    def test_adapter_config_validation(self):
        """Test adapter config token validation."""
        from pydantic import ValidationError

        # Invalid app token
        with pytest.raises(ValidationError):
            SlackAdapterConfig(app_token="invalid", bot_token="xoxb-valid")

        # Invalid bot token
        with pytest.raises(ValidationError):
            SlackAdapterConfig(app_token="xapp-valid", bot_token="invalid")

        # Both valid - now returns SecretStr
        config = SlackAdapterConfig(app_token="xapp-valid", bot_token="xoxb-valid")
        assert config.app_token.get_secret_value() == "xapp-valid"
        assert config.bot_token.get_secret_value() == "xoxb-valid"


class TestMentions:
    """Tests for mention utility functions."""

    def test_mention_user_with_user_object(self):
        """Test mention_user formats correctly with User object."""
        from chatom.slack import SlackUser

        user = SlackUser(id="U12345", name="testuser")
        result = mention_user(user)
        assert result == "<@U12345>"

    def test_mention_channel_with_channel_object(self):
        """Test mention_channel formats correctly with Channel object."""
        from chatom.slack import SlackChannel

        channel = SlackChannel(id="C12345", name="test-channel")
        result = mention_channel(channel)
        assert result == "<#C12345>"

    def test_mention_here(self):
        """Test mention_here formats correctly."""
        assert mention_here() == "<!here>"

    def test_mention_channel_all(self):
        """Test mention_channel_all formats correctly."""
        assert mention_channel_all() == "<!channel>"

    def test_mention_everyone(self):
        """Test mention_everyone formats correctly."""
        assert mention_everyone() == "<!everyone>"


@pytest.mark.skipif(not HAS_CSP, reason="CSP not installed")
class TestSlackAdapter:
    """Tests for SlackAdapter class."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock Slack config."""
        return SlackConfig(
            bot_token="xoxb-test-token",
            app_token="xapp-test-token",
        )

    @pytest.fixture
    def mock_backend(self):
        """Create a mock SlackBackend."""
        backend = MagicMock()
        backend.name = "slack"
        backend.format = "slack_markdown"
        backend.connected = True
        backend.config = SlackConfig(bot_token="xoxb-test", app_token="xapp-test")
        return backend

    def test_adapter_creation(self, mock_config):
        """Test SlackAdapter can be created."""
        with patch("csp_adapter_slack.adapter.SlackBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend.config = mock_config
            mock_backend_class.return_value = mock_backend

            adapter = SlackAdapter(mock_config)
            assert adapter.config == mock_config
            assert adapter.slack_backend is not None

    def test_adapter_config_property(self, mock_config):
        """Test config property returns the config."""
        with patch("csp_adapter_slack.adapter.SlackBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend.config = mock_config
            mock_backend_class.return_value = mock_backend

            adapter = SlackAdapter(mock_config)
            assert adapter.config == mock_config

    def test_adapter_backend_property(self, mock_config):
        """Test slack_backend property returns the backend."""
        with patch("csp_adapter_slack.adapter.SlackBackend") as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend.config = mock_config
            mock_backend_class.return_value = mock_backend

            adapter = SlackAdapter(mock_config)
            assert adapter.slack_backend == mock_backend


class TestSlackMessage:
    """Tests for SlackMessage from chatom."""

    def test_message_creation(self):
        """Test SlackMessage can be created."""
        from chatom.base import Channel

        msg = SlackMessage(
            channel=Channel(id="C12345"),
            content="Hello, World!",
        )
        assert msg.channel_id == "C12345"
        assert msg.content == "Hello, World!"

    def test_message_with_ts(self):
        """Test SlackMessage with timestamp using id field (ts is a property that returns id)."""
        from chatom.base import Channel

        msg = SlackMessage(
            channel=Channel(id="C12345"),
            content="Hello",
            id="1234567890.123456",
        )
        # ts property should return the id value
        assert msg.ts == "1234567890.123456"
        assert msg.id == "1234567890.123456"

    def test_message_with_thread_ts(self):
        """Test SlackMessage with thread timestamp (thread_ts is a property that returns thread.id)."""
        from chatom.base import Channel, Thread

        msg = SlackMessage(
            channel=Channel(id="C12345"),
            content="Reply in thread",
            thread=Thread(id="1234567890.123456"),
        )
        # thread_ts property should return the thread's id
        assert msg.thread_ts == "1234567890.123456"
        assert msg.thread.id == "1234567890.123456"


class TestExports:
    """Test that all expected exports are available."""

    def test_adapter_exports(self):
        """Test main exports are available."""
        from csp_adapter_slack import (
            SlackAdapter,
            SlackBackend,
            SlackConfig,
            SlackMessage,
            SlackPresenceStatus,
        )

        assert SlackAdapter is not None
        assert SlackBackend is not None
        assert SlackConfig is not None
        assert SlackMessage is not None
        assert SlackPresenceStatus is not None

    def test_mention_exports(self):
        """Test mention function exports are available."""
        from csp_adapter_slack import (
            mention_channel,
            mention_channel_all,
            mention_everyone,
            mention_here,
            mention_user,
        )

        assert mention_user is not None
        assert mention_channel is not None
        assert mention_user_group is not None
        assert mention_here is not None
        assert mention_channel_all is not None
        assert mention_everyone is not None

    def test_legacy_exports(self):
        """Test legacy exports for backwards compatibility."""
        from csp_adapter_slack import SlackAdapterConfig

        assert SlackAdapterConfig is not None
