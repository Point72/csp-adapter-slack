__all__ = ("mention_user",)


def mention_user(userid: str) -> str:
    """Convenience method, more difficult to do in symphony but we want slack to be symmetric"""
    if userid.startswith("<@") and userid.endswith(">"):
        return userid
    if userid.startswith("@"):
        return f"<{userid}>"
    return f"<@{userid}>"
