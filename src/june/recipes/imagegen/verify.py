"""Stdlib-only image artifact checks."""

from __future__ import annotations

_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_JPEG_SIG = b"\xff\xd8\xff"


def verify_image_bytes(
    data: bytes,
    *,
    min_bytes: int = 64,
    require_png: bool = True,
) -> list[dict[str, str]]:
    """Return a list of failure dicts (empty means ok)."""
    failures: list[dict[str, str]] = []
    if not data:
        failures.append({"reason": "empty_image"})
        return failures
    if len(data) < min_bytes:
        failures.append(
            {
                "reason": "too_small",
                "bytes": str(len(data)),
                "min_bytes": str(min_bytes),
            }
        )
    if require_png and not data.startswith(_PNG_SIG):
        failures.append({"reason": "not_png"})
    elif not require_png and not (
        data.startswith(_PNG_SIG) or data.startswith(_JPEG_SIG)
    ):
        failures.append({"reason": "unsupported_format"})
    return failures
