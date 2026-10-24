"""Platform filesystem primitives: a rename that can never overwrite.

* Windows: ``os.rename`` refuses to replace an existing destination.
* Linux: ``renameat2(..., RENAME_NOREPLACE)`` is atomic and never replaces.
* Anything else (or a filesystem without support): raise
  NoClobberUnsupportedError so the caller refuses the operation (fail closed).
"""

from __future__ import annotations

import ctypes
import errno
import os
import platform
import sys
from pathlib import Path

from tidymind.errors import NoClobberUnsupportedError

_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
_SYS_RENAMEAT2_X86_64 = 316
_UNSUPPORTED_ERRNOS = {errno.ENOSYS, errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP}


def _renameat2_noreplace(source: bytes, destination: bytes) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    function = getattr(libc, "renameat2", None)
    if function is not None:
        function.restype = ctypes.c_int
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        result = function(_AT_FDCWD, source, _AT_FDCWD, destination, _RENAME_NOREPLACE)
    elif platform.machine().lower() in ("x86_64", "amd64"):
        result = libc.syscall(_SYS_RENAMEAT2_X86_64, _AT_FDCWD, source, _AT_FDCWD, destination, _RENAME_NOREPLACE)
    else:
        raise NoClobberUnsupportedError("renameat2 is not available on this system")
    if result != 0:
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            raise FileExistsError(code, os.strerror(code))
        if code in _UNSUPPORTED_ERRNOS:
            raise NoClobberUnsupportedError(code, os.strerror(code))
        raise OSError(code, os.strerror(code))


def no_clobber_rename(source: Path, destination: Path) -> None:
    """Move ``source`` to ``destination`` without ever replacing anything."""
    if sys.platform == "win32":
        os.rename(source, destination)  # noqa: PTH104 - raises FileExistsError on conflict
    elif sys.platform.startswith("linux"):
        _renameat2_noreplace(os.fsencode(source), os.fsencode(destination))
    else:
        raise NoClobberUnsupportedError(f"no-overwrite rename is not supported on platform '{sys.platform}'")
