"""Chịu lỗi Gemini: timeout, mất kết nối, quá tải. Chỉ dùng pipeline + llm nên chạy được trên CẢ HAI
bản (Mission 2 để lấy bằng chứng Before, Mission 3 để lấy After)."""
import os
import sys
from datetime import date
from pathlib import Path

os.environ["EMBEDDER"] = "hash"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import llm
import pipeline

TODAY = date(2026, 10, 12)


def _with_gemini(fn):
    old = {k: os.environ.get(k) for k in ("LLM_PROVIDER", "GEMINI_API_KEY")}
    os.environ["LLM_PROVIDER"], os.environ["GEMINI_API_KEY"] = "gemini", "khoa-gia"
    try:
        return fn()
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def _survives(monkeypatch, exc):
    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(llm.urllib.request, "urlopen", boom)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    r = _with_gemini(lambda: pipeline.run("linh", "Quy định nghỉ phép của tôi như thế nào?", today=TODAY))
    assert r["type"] == "answer" and "14" in r["message"]     # vẫn trả lời đúng, từ tài liệu gốc


def test_read_timeout_does_not_crash(monkeypatch):
    _survives(monkeypatch, TimeoutError("The read operation timed out"))


def test_connection_reset_does_not_crash(monkeypatch):
    _survives(monkeypatch, ConnectionResetError("reset"))