"""Cấu hình: đọc .env rồi đến biến môi trường. Không dùng thư viện ngoài."""
import os
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"


def _load_env():
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.split(" #", 1)[0]          # bỏ comment cuối dòng
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()


def get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# --- LLM
def gemini_key() -> str:
    return get("GEMINI_API_KEY")


def chat_model() -> str:
    return get("GEMINI_CHAT_MODEL", "gemini-3.1-flash-lite")


def provider() -> str:
    """'gemini' nếu có GEMINI_API_KEY, ngược lại 'local' (chạy được không cần API)."""
    p = get("LLM_PROVIDER", "auto").lower()
    return ("gemini" if gemini_key() else "local") if p == "auto" else p


# --- Embedding / Qdrant
def embedder() -> str:
    return get("EMBEDDER", "bge-m3")          # "hash" chỉ dùng để test offline


def embed_model() -> str:
    return get("EMBED_MODEL", "BAAI/bge-m3")


def qdrant_url() -> str:
    return get("QDRANT_URL")                  # rỗng = Qdrant nhúng :memory:


# --- Ngưỡng truy xuất
def coverage_min() -> float:
    return float(get("COVERAGE_MIN", "0.5"))


def ambiguity_ratio() -> float:
    return float(get("AMBIGUITY_RATIO", "0.8"))