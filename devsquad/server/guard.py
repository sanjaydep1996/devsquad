# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Request checks that keep the local studio server usable only by its own pages."""

import urllib.parse
from typing import Optional

LOCAL_HOSTNAMES = ("localhost", "127.0.0.1", "::1")


def is_local_host(host_header: Optional[str]) -> bool:
    """False when another site name was pointed at this computer (DNS rebinding)."""
    if host_header is None:
        return True
    return urllib.parse.urlsplit(f"//{host_header}").hostname in LOCAL_HOSTNAMES


def origin_is_this_server(origin: Optional[str], port: Optional[int]) -> bool:
    """True for the studio's own pages and for command-line tools, which send no Origin.

    Browsers attach Origin to cross-site POSTs and WebSockets, so another website
    can't start tasks or inject failures on a developer's machine.
    """
    if origin is None:
        return True
    parsed = urllib.parse.urlsplit(origin)
    try:
        origin_port = parsed.port
    except ValueError:
        return False
    return parsed.hostname in LOCAL_HOSTNAMES and origin_port == port


def origin_matches_host(origin: Optional[str], host_header: Optional[str]) -> bool:
    """Same check for servers that don't know their own port: the page's origin must be the host it is calling."""
    if origin is None:
        return True
    if host_header is None:
        return False
    try:
        host_port = urllib.parse.urlsplit(f"//{host_header}").port or 80
    except ValueError:
        return False
    return origin_is_this_server(origin, host_port)
