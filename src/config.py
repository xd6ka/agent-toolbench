"""Configuration for the tool-using agent. Every value is env-overridable."""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.getenv("AGENT_MODEL", "qwen2.5:3b")
MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "8"))
TEMPERATURE = float(os.getenv("AGENT_TEMPERATURE", "0.1"))
TIMEOUT = float(os.getenv("AGENT_TIMEOUT", "180"))
# Ollama can constrain decoding to valid JSON; this is the difference between a
# parser that works on every call and one that works on most of them.
JSON_MODE = os.getenv("AGENT_JSON_MODE", "1") == "1"
MAX_OBS_CHARS = int(os.getenv("AGENT_MAX_OBS", "1200"))
# Number of worked examples put in front of the question. Zero is the honest
# baseline; anything else is a measured ablation, not a hidden improvement.
SHOTS = int(os.getenv("AGENT_SHOTS", "0"))
