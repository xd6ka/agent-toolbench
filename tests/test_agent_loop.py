import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from eval.fixtures import build_workspace  # noqa: E402
from src import agent  # noqa: E402


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('{"tool": "calc", "args": {"expression": "2+2"}}', "calc"),
        ('```json\n{"final": "42"}\n```', "final"),
        ('Sure. {"tool": "read_file", "args": {"path": "notes/alpha.txt"}} done', "read_file"),
        ('{"tool": "x", "args": {"a": {"b": 1}}}', "x"),
    ],
)
def test_extract_json_tolerates_real_replies(raw, expected):
    parsed = agent.extract_json(raw)
    assert parsed is not None
    if expected == "final":
        assert "final" in parsed
    else:
        assert parsed.get("tool") == expected


@pytest.mark.parametrize(
    "raw",
    ["no json here", '{"tool": "x", "args": {', '{"broken": 1}', ""],
)
def test_extract_json_returns_none_when_there_is_no_action(raw):
    parsed = agent.extract_json(raw)
    assert parsed is None or ("tool" not in parsed and "final" not in parsed)


def test_repair_turn_recovers_from_a_bad_reply(monkeypatch, tmp_path):
    ws = build_workspace(tmp_path / "ws")
    replies = [
        {"text": "I will read the file", "seconds": 1.0, "prompt_tokens": 10, "gen_tokens": 5},
        {"text": '{"tool": "read_file", "args": {"path": "notes/alpha.txt"}}', "seconds": 1.0, "prompt_tokens": 10, "gen_tokens": 5},
        {"text": '{"final": "2021"}', "seconds": 1.0, "prompt_tokens": 10, "gen_tokens": 5},
    ]
    calls = []

    def fake_chat(messages, **kwargs):
        calls.append(list(messages))
        return replies[len(calls) - 1]

    monkeypatch.setattr(agent.llm, "chat", fake_chat)
    result = agent.run("In what year did Project Atlas start?", ws)
    assert result["answer"] == "2021"
    assert result["parse_errors"] == 1
    assert result["steps"] == 3
    assert "Project Atlas" in result["trace"][1]["observation"]


def test_tool_error_becomes_an_observation_not_a_crash(monkeypatch, tmp_path):
    ws = build_workspace(tmp_path / "ws")
    replies = [
        {"text": '{"tool": "read_file", "args": {"path": "notes/gama.txt"}}', "seconds": 1.0, "prompt_tokens": 10, "gen_tokens": 5},
        {"text": '{"final": "no such file"}', "seconds": 1.0, "prompt_tokens": 10, "gen_tokens": 5},
    ]
    calls = []

    def fake_chat(messages, **kwargs):
        calls.append(list(messages))
        return replies[len(calls) - 1]

    monkeypatch.setattr(agent.llm, "chat", fake_chat)
    result = agent.run("Read notes/gama.txt", ws)
    assert result["trace"][0]["error"].startswith("file not found")
    assert result["answer"] == "no such file"


def test_step_limit_is_reported_not_faked(monkeypatch, tmp_path):
    ws = build_workspace(tmp_path / "ws")

    def fake_chat(messages, **kwargs):
        return {"text": '{"tool": "list_files", "args": {}}', "seconds": 1.0, "prompt_tokens": 10, "gen_tokens": 5}

    monkeypatch.setattr(agent.llm, "chat", fake_chat)
    result = agent.run("loop forever", ws, max_steps=2)
    assert result["status"] == "step_limit"
    assert result["answer"] is None
