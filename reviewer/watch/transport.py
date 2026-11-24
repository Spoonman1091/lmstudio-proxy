"""Minimal JSON-over-HTTP POST using only the standard library."""
from __future__ import annotations

import json
import urllib.request
from typing import Any, Mapping


def post_json(url: str, payload: Mapping[str, Any], timeout: float) -> Mapping[str, Any]:
    request = urllib.request.Request(  # noqa: S310 - URL comes from our own config
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))
