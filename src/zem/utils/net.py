"""What the shell is willing to download from.

Two commands fetch files that then run or shape the shell: `hints
install` (a spec may run commands on TAB) and `theme install`. Both go
through :func:`check_url`, so the policy lives in one place.
"""

from __future__ import annotations

from urllib.parse import urlsplit

#: Hosts where plain http is acceptable: a registry served from this
#: machine while developing specs or themes.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class UnsafeURL(ValueError):
    """The URL uses a scheme or host the shell refuses to fetch from."""


def check_url(url: str) -> None:
    """Raise :class:`UnsafeURL` unless ``url`` is https, or http to this host.

    A spec's SHA-256 comes from the same index as the spec itself, so
    over plain http it protects against nothing; and `file://` would turn
    "install from a URL" into "read any file".
    """
    parts = urlsplit(url)
    if parts.scheme == "https" and parts.hostname:
        return
    if parts.scheme == "http" and parts.hostname in LOCAL_HOSTS:
        return
    raise UnsafeURL(
        f"refusing to fetch {url!r}: only https:// URLs are accepted "
        "(http:// only for localhost)"
    )
