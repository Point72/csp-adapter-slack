from typing import List

from csp.impl.struct import Struct

__all__ = ("SlackMessage",)


class SlackMessage(Struct):
    user: str
    """name of the author of the message"""

    user_email: str
    """email of the author of the message, if available"""

    user_id: str
    """platform-specific id of the author of the message, if available"""

    tags: List[str]
    """list of users tagged in the `msg` of the message"""

    channel: str
    """name of the channel for the slack message, if available"""

    channel_id: str
    """id of the channel for the slack message, if available"""

    channel_type: str
    """type of the channel. either "message", "public", or "private" """

    msg: str
    """parsed text of the message"""

    reaction: str
    """emoji reaction to put on a thread. Exclusive with `msg`, requires `thread`"""

    thread: str
    """thread to post msg under, or msg id on which to apply reaction"""

    payload: dict
    """raw slack message payload"""
