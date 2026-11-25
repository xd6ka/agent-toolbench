import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from src.sandbox import SandboxError, resolve, resolve_for_write  # noqa: E402


def test_resolve_accepts_a_path_inside(tmp_path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "a.txt").write_text("x", encoding="utf-8")
    assert resolve(tmp_path, "notes/a.txt") == (tmp_path / "notes" / "a.txt").resolve()


@pytest.mark.parametrize("path", ["../outside.txt", "notes/../../etc/passwd", "/etc/passwd"])
def test_resolve_refuses_escapes(tmp_path, path):
    with pytest.raises(SandboxError):
        resolve(tmp_path, path)


def test_write_refuses_the_database_directory(tmp_path):
    (tmp_path / "db").mkdir()
    (tmp_path / "db" / "shop.sqlite").write_text("x", encoding="utf-8")
    with pytest.raises(SandboxError):
        resolve_for_write(tmp_path, "db/shop.sqlite")


def test_write_refuses_the_root_and_empty_paths(tmp_path):
    with pytest.raises(SandboxError):
        resolve_for_write(tmp_path, ".")
    with pytest.raises(SandboxError):
        resolve(tmp_path, "")
