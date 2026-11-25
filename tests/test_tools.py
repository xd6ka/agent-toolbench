import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from eval.fixtures import build_workspace  # noqa: E402
from src.tools import ToolError, calc, call_tool, list_files, read_file, search_text, sql_query, write_file  # noqa: E402


@pytest.fixture()
def ws(tmp_path):
    return build_workspace(tmp_path / "ws")


def test_calc_evaluates_arithmetic_and_rounds_floats():
    assert calc("4200 * 0.17") == "714.0"
    assert calc("128 * 7 + 25") == "921"


@pytest.mark.parametrize("expr", ["__import__('os').system('dir')", "open('x')", "2 ** 10000 * 0"])
def test_calc_refuses_anything_that_is_not_arithmetic(expr):
    with pytest.raises(ToolError):
        calc(expr)


def test_read_file_truncates_and_reports_missing(ws):
    assert "Project Atlas" in read_file(ws, "notes/alpha.txt")
    with pytest.raises(ToolError):
        read_file(ws, "notes/gama.txt")


def test_read_file_refuses_escape(ws):
    with pytest.raises(ToolError):
        read_file(ws, "../outside.txt")


def test_list_files_lists_the_tree(ws):
    listing = list_files(ws, "notes/*.txt")
    assert "notes/alpha.txt" in listing and "notes/instructions.txt" in listing
    assert "sales.csv" not in listing


def test_search_text_finds_the_rack_file(ws):
    hits = search_text(ws, "Hangzhou")
    assert "notes/beta.txt:1" in hits
    assert search_text(ws, "no-such-phrase") == "(no matches)"


def test_sql_query_counts_rows_and_refuses_writes(ws):
    assert sql_query(ws, "select count(*) from orders") == "12"
    with pytest.raises(ToolError):
        sql_query(ws, "delete from orders")
    with pytest.raises(ToolError):
        sql_query(ws, "select 1; select 2")


def test_write_file_writes_and_refuses_protected_dirs(ws):
    assert "wrote" in write_file(ws, "report/total.txt", "29")
    assert (ws / "report" / "total.txt").read_text(encoding="utf-8") == "29"
    with pytest.raises(ToolError):
        write_file(ws, "db/shop.sqlite", "x")


def test_call_tool_rejects_unknown_names_and_unexpected_args(ws):
    with pytest.raises(ToolError, match="unknown tool"):
        call_tool(ws, "delete_file", {"path": "notes/alpha.txt"})
    with pytest.raises(ToolError, match="unexpected arguments"):
        call_tool(ws, "read_file", {"path": "notes/alpha.txt", "sudo": True})
