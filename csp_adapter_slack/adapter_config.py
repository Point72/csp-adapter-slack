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
        assert v.startswith("xapp-"), "App token must start with 'xapp-'"
        return v

    @field_validator("bot_token")
    def validate_bot_token(cls, v):
        assert v.startswith("xoxb-"), "Bot token must start with 'xoxb-'"
        return v

    @field_validator("ssl")
    def validate_ssl(cls, v):
        # TODO pydantic validation via schema
        assert v is None or isinstance(v, SSLContext)
        return v
