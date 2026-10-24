"""A process-wide check that every file write lands in predicate_correctness/output/ (p10.md subtask 3).

`install()` adds a Python audit hook (sys.addaudithook; it cannot be removed again). From then on, in this process:
  - opening a file for writing, creating or removing a folder, renaming or removing a file outside the allowed folders
    raises PermissionError (the write does not happen). A relative path given with dir_fd (an open folder, as
    shutil.rmtree uses) is taken inside that folder (eval v2 fix F1 item 8a); if that folder cannot be found, the
    write is refused;
  - under ~/ShieldAgent, opening any file (also for reading) and listing a folder (os.listdir, os.scandir, os.walk,
    os.fwalk, glob, pathlib glob/walk, os.chdir, xattr reads) raise PermissionError (F1 item 8b);
  - not blocked, because Python raises no audit event for them: os.stat / os.lstat, os.path.exists / isdir / isfile,
    os.access, os.readlink, os.path.realpath. They show names, sizes and times under ~/ShieldAgent, never content;
  - not seen: os.open(name, ..., dir_fd=fd) gives the hook no dir_fd, so a relative name is taken from the current
    folder (no runner code does this; shutil.rmtree opens only for reading this way);
  - /dev/null and the other /dev/ files are allowed.
Every refused access is also counted in `REFUSED` (for the run's log).

Standard library only. Used by guard/run_online.py; never imports gold code.
"""
from __future__ import annotations

import os
import sys
import threading
from typing import Iterable, List, Optional

PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PC_DIR, "output")
FORBIDDEN_ROOTS = (os.path.realpath(os.path.expanduser("~/ShieldAgent")),)
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
_PATH_EVENTS = {          # event -> (position of a path argument, position of its dir_fd argument or None), ...
    "os.mkdir": ((0, 2),), "os.rmdir": ((0, 1),), "os.remove": ((0, 1),), "os.rename": ((0, 2), (1, 3)),
    "os.symlink": ((0, None), (1, 2)), "os.link": ((0, 2), (1, 3)), "os.truncate": ((0, None),),
    "os.chmod": ((0, 2),), "os.chown": ((0, 3),), "os.utime": ((0, 3),),
    "shutil.copyfile": ((1, None),), "shutil.copytree": ((1, None),), "shutil.move": ((1, None),),
    "shutil.rmtree": ((0, 1),),
}
_LIST_EVENTS = {          # reads that list a folder (refused under ~/ShieldAgent): event -> positions of paths
    "os.listdir": (0,), "os.scandir": (0,), "os.walk": (0,), "os.fwalk": (0,), "glob.glob": (0,),
    "glob.glob/2": (0, 2), "pathlib.Path.glob": (0,), "pathlib.Path.rglob": (0,), "pathlib.Path.walk": (0,),
    "os.chdir": (0,), "os.listxattr": (0,), "os.getxattr": (0,),
}
_UNKNOWN = object()       # a dir_fd whose folder cannot be found

_state = {"installed": False, "allowed": [], "lock": threading.Lock()}
REFUSED: List[str] = []


def _fd_path(fd: int) -> Optional[str]:
    """The folder (or file) an open file descriptor points to, from /proc/self/fd; None if unknown."""
    try:
        p = os.readlink(f"/proc/self/fd/{fd}")
    except (OSError, ValueError):
        return None
    if not p.startswith("/") or p.endswith(" (deleted)"):
        return None
    return p


def _given_fd(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 0


def _norm(p, dir_fd=None):
    """The real absolute path of a path argument. None for a file descriptor (already open) or no path. A relative
    path with a dir_fd (>= 0) is taken inside that folder; _UNKNOWN if that folder cannot be found."""
    if isinstance(p, int) or p is None:
        return None                      # a file descriptor: already open
    try:
        s = os.fsdecode(p)
    except (TypeError, ValueError):
        return None
    if _given_fd(dir_fd) and not os.path.isabs(s):
        base = _fd_path(dir_fd)
        if base is None:
            return _UNKNOWN
        s = os.path.join(base, s)
    try:
        return os.path.realpath(s)
    except (TypeError, ValueError):
        return None


def _under(path: str, roots: Iterable[str]) -> bool:
    return any(path == r or path.startswith(r.rstrip(os.sep) + os.sep) for r in roots)


def is_allowed_write(path: str, allowed: Optional[Iterable[str]] = None, dir_fd=None) -> bool:
    p = _norm(path, dir_fd)
    if p is None:
        return True
    if p is _UNKNOWN:
        return False
    if p.startswith("/dev/"):
        return True
    if _under(p, FORBIDDEN_ROOTS):
        return False
    return _under(p, allowed if allowed is not None else _state["allowed"])


def _refuse(what: str) -> None:
    REFUSED.append(what)
    raise PermissionError(f"write guard (Part 10): refused {what}")


def _listed_path(x):
    """A folder argument of a listing event: a path, an open folder's file descriptor (os.scandir(fd)), or None
    (the current folder, as os.listdir() with no argument)."""
    if _given_fd(x):
        p = _fd_path(x)
        return os.path.realpath(p) if p else None
    if x is None:
        try:
            return os.path.realpath(os.getcwd())
        except OSError:
            return None
    return _norm(x)


def _hook(event: str, args: tuple) -> None:
    if event == "open":
        if not args:
            return
        p = _norm(args[0])
        if p is None:
            return
        if _under(p, FORBIDDEN_ROOTS):
            _refuse(f"open {p}")
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else 0
        writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or \
                  (isinstance(flags, int) and bool(flags & _WRITE_FLAGS))
        if writing and not is_allowed_write(p):
            _refuse(f"write {p}")
        return
    pos = _PATH_EVENTS.get(event)
    if pos:
        for i, j in pos:
            if i < len(args):
                fd = args[j] if j is not None and j < len(args) else None
                p = _norm(args[i], fd)
                if p is _UNKNOWN:
                    _refuse(f"{event} {os.fsdecode(args[i])!r} in dir_fd {fd} (folder unknown)")
                if p is not None and not is_allowed_write(p):
                    _refuse(f"{event} {p}")
        return
    lpos = _LIST_EVENTS.get(event)
    if lpos:
        for i in lpos:
            if i < len(args):
                p = _listed_path(args[i])
                if isinstance(p, str) and _under(p, FORBIDDEN_ROOTS):
                    _refuse(f"{event} {p}")


def install(allowed: Iterable[str] = (OUTPUT_DIR,)) -> List[str]:
    """Install the hook once. `allowed`: folders where writes are allowed (default: predicate_correctness/output/).
    Calling it again only checks that the allowed folders are the same."""
    roots = [os.path.realpath(r) for r in allowed]
    for r in roots:
        if _under(r, FORBIDDEN_ROOTS):
            raise ValueError(f"cannot allow writes under {r}")
    with _state["lock"]:
        if _state["installed"]:
            if roots != _state["allowed"]:
                raise RuntimeError("write guard already installed with other folders")
            return roots
        _state["allowed"] = roots
        sys.addaudithook(_hook)
        _state["installed"] = True
    return roots


def installed() -> bool:
    return _state["installed"]
