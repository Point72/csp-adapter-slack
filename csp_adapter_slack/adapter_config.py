from pathlib import Path
from ssl import SSLContext
from typing import Optional

from pydantic import BaseModel, Field, field_validator

__all__ = ("SlackAdapterConfig",)


class SlackAdapterConfig(BaseModel):
    """A config class that holds the required information to interact with Slack."""

    app_token: str = Field(description="The app token for the Slack bot")
    bot_token: str = Field(description="The bot token for the Slack bot")
    ssl: Optional[object] = None

    @field_validator("app_token")
    def validate_app_token(cls, v):
        if v.startswith("xapp-"):
            return v
        elif Path(v).exists():
            return Path(v).read_text().strip()
        raise ValueError("App token must start with 'xoxb-' or be a file path")

    @field_validator("bot_token")
    def validate_bot_token(cls, v):
        if v.startswith("xoxb-"):
            return v
        elif Path(v).exists():
            return Path(v).read_text().strip()
        raise ValueError("Bot token must start with 'xoxb-' or be a file path")

    @field_validator("ssl")
    def validate_ssl(cls, v):
        # TODO pydantic validation via schema
        assert v is None or isinstance(v, SSLContext)
        return v
