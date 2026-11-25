"""Path jail for every file tool.

The agent is allowed to read and write only inside the workspace it was given.
Every path goes through `resolve`, which refuses anything that escapes the root
(absolute paths, `..` segments, symlinks pointing outside). Tools never open a
path they resolved themselves.
"""
from pathlib import Path


class SandboxError(Exception):
    """Raised when a path is outside the workspace or otherwise refused."""


# Directories the agent may read but must not modify: the fixture database is
# evidence, and an agent that can rewrite its own evidence can "pass" anything.
PROTECTED_DIRS = ("db",)


def resolve(root: Path, path: str) -> Path:
    root = Path(root).resolve()
    raw = (path or "").strip()
    if not raw:
        raise SandboxError("empty path")
    candidate = Path(raw)
    target = (candidate if candidate.is_absolute() else (root / candidate)).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise SandboxError(f"path escapes the workspace: {raw}") from None
    return target


def resolve_for_write(root: Path, path: str) -> Path:
    target = resolve(root, path)
    root = Path(root).resolve()
    for name in PROTECTED_DIRS:
        if target == root / name or root / name in target.parents:
            raise SandboxError(f"{name}/ is read-only")
    if target == root:
        raise SandboxError("cannot write to the workspace root itself")
    return target
