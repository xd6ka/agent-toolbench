"""The six tools the agent can call, plus validation and dispatch.

Each tool is a plain function that takes the workspace root and named arguments
and returns a short observation string. Failures raise ToolError, which the
agent loop turns into an observation the model can react to — the model never
sees a Python traceback.
"""
import ast
import operator
import sqlite3
from pathlib import Path

from .sandbox import SandboxError, resolve, resolve_for_write

MAX_READ_CHARS = 1000
MAX_LIST_ENTRIES = 60
MAX_SEARCH_HITS = 20

# --- arithmetic -------------------------------------------------------------

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


class ToolError(Exception):
    """A tool refused or failed; the message is safe to show the model."""


def _eval_ast(node):
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left = _eval_ast(node.left)
        right = _eval_ast(node.right)
        # A tiny expression can still ask for a 3000-digit integer; that is a
        # denial of service, not arithmetic.
        if isinstance(node.op, ast.Pow) and abs(right) > 32:
            raise ToolError("exponent too large")
        return _BINOPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval_ast(node.operand))
    raise ToolError("unsupported expression: only numbers and + - * / // % ** are allowed")


def calc(expression: str) -> str:
    expr = (expression or "").strip()
    if not expr or len(expr) > 200:
        raise ToolError("calc needs a short arithmetic expression")
    try:
        tree = ast.parse(expr, mode="eval")
        value = _eval_ast(tree)
    except SyntaxError:
        raise ToolError(f"not an arithmetic expression: {expr}") from None
    except ZeroDivisionError:
        raise ToolError("division by zero")
    if isinstance(value, (int, float)) and abs(value) > 1e12:
        raise ToolError("result is out of range")
    if isinstance(value, float):
        value = round(value, 6)
    return f"{value}"


# --- file tools -------------------------------------------------------------


def list_files(root: Path, glob: str = "**/*") -> str:
    root = Path(root).resolve()
    pattern = (glob or "**/*").strip()
    if pattern.startswith("/") or ".." in Path(pattern).parts:
        raise ToolError("glob must stay inside the workspace")
    hits = sorted(p for p in root.glob(pattern) if p.is_file() and "venv" not in p.parts)
    if not hits:
        return "(no files match)"
    lines = []
    for p in hits[:MAX_LIST_ENTRIES]:
        rel = p.relative_to(root).as_posix()
        lines.append(f"{rel} ({p.stat().st_size} bytes)")
    if len(hits) > MAX_LIST_ENTRIES:
        lines.append(f"... {len(hits) - MAX_LIST_ENTRIES} more")
    return "\n".join(lines)


def read_file(root: Path, path: str, max_chars: int = MAX_READ_CHARS) -> str:
    try:
        target = resolve(root, path)
    except SandboxError as exc:
        raise ToolError(str(exc)) from None
    if not target.exists():
        raise ToolError(f"file not found: {path}")
    if not target.is_file():
        raise ToolError(f"not a file: {path}")
    text = target.read_text(encoding="utf-8", errors="replace")
    budget = max(80, min(int(max_chars or MAX_READ_CHARS), MAX_READ_CHARS))
    if len(text) > budget:
        return text[:budget] + f"\n[... truncated at {budget} chars of {len(text)}]"
    return text


def write_file(root: Path, path: str, content: str) -> str:
    try:
        target = resolve_for_write(root, path)
    except SandboxError as exc:
        raise ToolError(str(exc)) from None
    if len(content or "") > 2000:
        raise ToolError("refusing to write more than 2000 chars")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content or "", encoding="utf-8")
    return f"wrote {len(content or '')} chars to {path}"


def search_text(root: Path, query: str) -> str:
    query = (query or "").strip()
    if len(query) < 2:
        raise ToolError("search_text needs at least 2 characters")
    root = Path(root).resolve()
    hits = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or "venv" in p.parts or p.suffix in {".sqlite", ".db"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if query.lower() in line.lower():
                hits.append(f"{p.relative_to(root).as_posix()}:{number}: {line.strip()[:120]}")
                if len(hits) >= MAX_SEARCH_HITS:
                    return "\n".join(hits)
    return "\n".join(hits) if hits else "(no matches)"


def _schema(con: sqlite3.Connection) -> str:
    """One-line description of the tables, so a failed query can teach."""
    try:
        names = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        parts = []
        for name in names:
            cols = [row[1] for row in con.execute(f"PRAGMA table_info({name})")]
            parts.append(f"{name}({', '.join(cols)})")
        return "; ".join(parts) or "no tables"
    except sqlite3.Error:
        return "schema unavailable"


def sql_query(root: Path, sql: str) -> str:
    sql = (sql or "").strip()
    lowered = sql.lower()
    if not lowered.startswith("select"):
        raise ToolError("only SELECT statements are allowed")
    if ";" in sql.rstrip(";"):
        raise ToolError("one statement at a time")
    db = Path(root).resolve() / "db" / "shop.sqlite"
    if not db.exists():
        raise ToolError("db/shop.sqlite is missing")
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise ToolError(f"cannot open the database: {exc}") from None
    try:
        rows = con.execute(sql).fetchmany(50)
    except sqlite3.Error as exc:
        # A failing query should say what does exist: guessing table names is
        # usually the model's next move, and it is cheaper to answer than to
        # let it burn steps. Same reason the hint names the other tool.
        raise ToolError(
            f"SQL error: {exc}. Schema: {_schema(con)}. "
            "Notes and csv files are not in this database - read them with read_file."
        ) from None
    finally:
        con.close()
    if not rows:
        return "(no rows)"
    return "\n".join(" | ".join(str(c) for c in row) for row in rows)


# --- registry ---------------------------------------------------------------

TOOLS = {
    "list_files": {
        "fn": list_files,
        "params": {"glob": "glob pattern, default **/*"},
        "help": "list files in the workspace, e.g. list_files(glob='notes/*.txt')",
    },
    "read_file": {
        "fn": read_file,
        "params": {"path": "relative path", "max_chars": "optional cap, default 1000"},
        "help": "read a text file, e.g. read_file(path='notes/alpha.txt')",
    },
    "write_file": {
        "fn": write_file,
        "params": {"path": "relative path", "content": "text to write, max 2000 chars"},
        "help": "write a text file; db/ is read-only",
    },
    "search_text": {
        "fn": search_text,
        "params": {"query": "substring, at least 2 chars"},
        "help": "find which file contains a phrase, returns path:line",
    },
    "calc": {
        # `calc` itself takes one argument; every other tool takes the workspace
        # root first. The adapter keeps the registry uniform for dispatch.
        "fn": lambda root, expression: calc(expression),
        "params": {"expression": "arithmetic only, e.g. '4200 * 0.17'"},
        "help": "evaluate arithmetic exactly",
    },
    "sql_query": {
        "fn": sql_query,
        "params": {"sql": "one SELECT statement against db/shop.sqlite"},
        "help": "run a read-only SQL query on the fixture database",
    },
}


def tool_names() -> list[str]:
    return sorted(TOOLS)


def describe_tools() -> str:
    lines = []
    for name in tool_names():
        spec = TOOLS[name]
        params = ", ".join(f"{k}: {v}" for k, v in spec["params"].items())
        lines.append(f"- {name}({params}) -> {spec['help']}")
    return "\n".join(lines)


def call_tool(root: Path, name: str, args: dict) -> str:
    spec = TOOLS.get(name)
    if spec is None:
        raise ToolError(f"unknown tool: {name}. Available: {', '.join(tool_names())}")
    if not isinstance(args, dict):
        raise ToolError("args must be a JSON object")
    accepted = set(spec["params"])
    unexpected = set(args) - accepted
    if unexpected:
        raise ToolError(f"unexpected arguments for {name}: {sorted(unexpected)}")
    try:
        return spec["fn"](root, **args)
    except TypeError as exc:
        raise ToolError(f"bad arguments for {name}: {exc}") from None
    except SandboxError as exc:
        raise ToolError(str(exc)) from None
