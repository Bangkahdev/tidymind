"""Terminal-safe text: file names and model text are untrusted display data."""

from __future__ import annotations

_BIDI = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A))


def safe_text(value: str) -> str:
    """Escape control, C1 and bidi-override characters so output cannot spoof the terminal."""
    out: list[str] = []
    for ch in value:
        code = ord(ch)
        if code < 32 or code == 127 or 0x80 <= code <= 0x9F:
            out.append(f"\\x{code:02x}")
        elif code in _BIDI:
            out.append(f"\\u{code:04x}")
        else:
            out.append(ch)
    return "".join(out)
