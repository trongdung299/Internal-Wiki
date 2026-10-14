"""Lõi tri thức Appota (theo kế hoạch Mission 1).

Cấu hình nằm ở config.py. Gồm 4 phần, đúng thứ tự luồng xử lý:
  1. Policy engine: lọc cứng bằng code (quyền + đơn vị + hiệu lực), TRƯỚC khi AI nhìn thấy dữ liệu
  2. Chunk theo cấu trúc (điều/khoản), thừa kế toàn bộ metadata
  3. Truy xuất hybrid: BM25 + embedding bge-m3 (Qdrant), gộp bằng RRF; quyền/đơn vị/hiệu lực
     được ép ngay tại truy vấn
  4. Phân giải xung đột bằng quy tắc (không dùng LLM)
"""
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import config


# ============================================================ 1. POLICY ENGINE
ACCESS_RANK = {"staff": 1, "manager": 2, "hr": 3}
REQUIRED_FIELDS = ["id", "doc_key", "title", "topic", "scope", "access_level", "version",
                   "effective_from", "status", "override_mode", "owner", "content"]
VALID_STATUS = {"draft", "active", "revoked"}
VALID_OVERRIDE = {"override", "floor", "additive"}


class MetadataError(ValueError):
    """Tài liệu thiếu/sai metadata: bị chặn nhập kho, không mặc định công khai."""


def validate_doc(doc: dict) -> None:
    missing = [f for f in REQUIRED_FIELDS if not doc.get(f)]
    if missing:
        raise MetadataError(f"{doc.get('id', '?')}: thiếu {missing}")
    if doc["access_level"] not in ACCESS_RANK:
        raise MetadataError(f"{doc['id']}: access_level không hợp lệ")
    if doc["status"] not in VALID_STATUS:
        raise MetadataError(f"{doc['id']}: status không hợp lệ")
    if doc["override_mode"] not in VALID_OVERRIDE:
        raise MetadataError(f"{doc['id']}: override_mode không hợp lệ")


def load_docs(path=config.DATA / "docs.json") -> list:
    docs = json.loads(Path(path).read_text(encoding="utf-8"))
    for d in docs:
        validate_doc(d)
    return docs


def _users_raw(path=config.DATA / "users.json") -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_users(path=config.DATA / "users.json") -> dict:
    """Đọc lại mỗi lần gọi = hồ sơ real-time (nhân sự chuyển đơn vị thì có hiệu lực ngay)."""
    return {u["id"]: u for u in _users_raw(path)["users"]}


def load_org(path=config.DATA / "users.json") -> dict:
    return _users_raw(path)["org"]


def unit_path(unit: str) -> list:
    """'appota/cty_a/marketing' -> ['appota', 'appota/cty_a', 'appota/cty_a/marketing']."""
    parts = unit.split("/")
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def _ymd(iso: str) -> int:
    return int(iso.replace("-", ""))


def build_conditions(user: dict, today: date) -> dict:
    """Điều kiện lọc lấy từ HỒ SƠ XÁC THỰC, không lấy gì từ câu hỏi."""
    return {"scope_in": unit_path(user["unit"]),
            "max_access": ACCESS_RANK[user["role"]],
            "today": today}


def check_doc(doc: dict, cond: dict):
    """(được_phép, lý_do_loại). Thứ tự: quyền -> phạm vi -> trạng thái -> hiệu lực."""
    if ACCESS_RANK[doc["access_level"]] > cond["max_access"]:
        return False, "access"
    if doc["scope"] not in cond["scope_in"]:
        return False, "scope"
    if doc["status"] != "active":
        return False, "status"
    if date.fromisoformat(doc["effective_from"]) > cond["today"]:
        return False, "not_yet_effective"
    if doc.get("effective_to") and date.fromisoformat(doc["effective_to"]) < cond["today"]:
        return False, "expired"
    return True, None


def filter_docs(docs: list, user: dict, today: date):
    """(allowed, rejected). `rejected` CHỈ để log/debug nội bộ, không đưa cho LLM hay người dùng."""
    cond = build_conditions(user, today)
    allowed, rejected = [], []
    for d in docs:
        ok, reason = check_doc(d, cond)
        if ok:
            allowed.append(d)
        else:
            rejected.append({"id": d["id"], "title": d["title"], "reason": reason})
    return allowed, rejected


# ============================================================ 2. CHUNK
def chunk_doc(doc: dict) -> list:
    """Chunk theo cấu trúc (Điều/Khoản/đầu dòng); nếu không có cấu trúc thì theo câu.
    Mỗi chunk gắn tiêu đề tài liệu và thừa kế toàn bộ metadata."""
    text = doc["content"].strip()
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if any(re.match(r"^(Điều|Khoản|\d+[.)])\s", l) for l in lines):
        parts = lines
    else:
        parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    out = []
    for i, p in enumerate(parts):
        out.append({
            "chunk_id": f"{doc['id']}#{i}", "doc_id": doc["id"], "topic": doc["topic"],
            "title": doc["title"], "text": p, "embed_text": f"{doc['title']}. {p}",
            "scope": doc["scope"], "access_rank": ACCESS_RANK[doc["access_level"]],
            "status": doc["status"], "from_int": _ymd(doc["effective_from"]),
            "to_int": _ymd(doc["effective_to"]) if doc.get("effective_to") else 99991231,
        })
    return out


# ============================================================ 3. TRUY XUẤT HYBRID
def tokens(text: str) -> list:
    """Âm tiết + bigram: đủ tốt cho BM25 tiếng Việt mà không cần tách từ."""
    w = re.findall(r"\w+", text.lower())
    return w + [a + "_" + b for a, b in zip(w, w[1:])]


def bm25_rank(query: str, chunks: list, k1: float = 1.5, b: float = 0.75) -> list:
    """Trả về [(chỉ số chunk, điểm)] giảm dần, chỉ gồm chunk có điểm > 0.
    IDF tính trên tập đã lọc quyền nên thống kê không rò rỉ từ tài liệu ngoài quyền."""
    if not chunks:
        return []
    docs = [tokens(c["embed_text"]) for c in chunks]
    n, avg = len(docs), sum(map(len, docs)) / len(docs)
    df = Counter(t for d in docs for t in set(d))
    q = set(tokens(query))
    scored = []
    for i, d in enumerate(docs):
        tf, s = Counter(d), 0.0
        for t in q & tf.keys():
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avg))
        if s > 0:
            scored.append((i, s))
    return sorted(scored, key=lambda x: -x[1])


def rrf(rank_lists: list, k: int = 60) -> dict:
    """Reciprocal Rank Fusion: mỗi danh sách là các khóa theo thứ tự xếp hạng."""
    score = defaultdict(float)
    for lst in rank_lists:
        for r, key in enumerate(lst):
            score[key] += 1.0 / (k + r + 1)
    return score


_BGE = None


def _hash_embed(texts: list):
    """Embedding băm giả lập, chỉ để test offline (EMBEDDER=hash). KHÔNG dùng khi chạy thật."""
    import numpy as np
    dim = 512
    out = np.zeros((len(texts), dim), dtype="float32")
    for i, t in enumerate(texts):
        for tok in tokens(t):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            out[i, h % dim] += 1.0 if (h >> 100) & 1 else -1.0
        n = np.linalg.norm(out[i])
        if n:
            out[i] /= n
    return out


def embed(texts: list, is_query: bool = False):
    """Embedding bge-m3 (dense, đã chuẩn hóa). Vector tài liệu được cache theo nội dung."""
    import numpy as np
    if config.embedder() == "hash":
        return _hash_embed(texts)
    model_name = config.embed_model()
    cache = None
    if not is_query:
        key = hashlib.sha1((model_name + "\n".join(texts)).encode()).hexdigest()[:16]
        cache = config.ROOT / ".cache" / f"emb_{key}.npy"
        if cache.exists():
            return np.load(cache)
    global _BGE
    if _BGE is None:
        from sentence_transformers import SentenceTransformer
        _BGE = SentenceTransformer(model_name)
    vecs = _BGE.encode(texts, normalize_embeddings=True, batch_size=16, show_progress_bar=False)
    vecs = np.asarray(vecs, dtype="float32")
    if cache is not None:
        cache.parent.mkdir(exist_ok=True)
        np.save(cache, vecs)
    return vecs


class Retriever:
    """Qdrant (dense bge-m3) + BM25, gộp bằng RRF.
    Qdrant: QDRANT_URL nếu có, ngược lại chế độ nhúng (:memory:).
    Dự phòng theo kế hoạch: Qdrant không khả dụng thì tính cosine bằng numpy."""
    COLLECTION = "appota_kb"

    def __init__(self, docs: list):
        self.chunks = [c for d in docs for c in chunk_doc(d)]
        self.vecs = embed([c["embed_text"] for c in self.chunks])
        self.backend, self.client = "numpy", None
        try:
            from qdrant_client import QdrantClient, models
            self._qm = models
            self.client = QdrantClient(url=config.qdrant_url()) if config.qdrant_url() \
                else QdrantClient(":memory:")
            if self.client.collection_exists(self.COLLECTION):
                self.client.delete_collection(self.COLLECTION)
            self.client.create_collection(
                self.COLLECTION,
                vectors_config=models.VectorParams(size=int(self.vecs.shape[1]),
                                                   distance=models.Distance.COSINE))
            self.client.upsert(self.COLLECTION, points=[
                models.PointStruct(id=i, vector=self.vecs[i].tolist(),
                                   payload={k: c[k] for k in (
                                       "chunk_id", "doc_id", "topic", "scope", "access_rank",
                                       "status", "from_int", "to_int")})
                for i, c in enumerate(self.chunks)])
            self.backend = "qdrant"
        except Exception as e:  # thiếu thư viện hoặc server không chạy
            self.client, self.fallback_reason = None, repr(e)

    def _dense(self, qv, cond: dict, allowed_ids: set, k: int) -> list:
        if self.client is not None:
            m, t = self._qm, _ymd(cond["today"].isoformat())
            flt = m.Filter(must=[  # ép quyền, đơn vị, hiệu lực NGAY TẠI TRUY VẤN
                m.FieldCondition(key="scope", match=m.MatchAny(any=cond["scope_in"])),
                m.FieldCondition(key="access_rank", range=m.Range(lte=cond["max_access"])),
                m.FieldCondition(key="status", match=m.MatchValue(value="active")),
                m.FieldCondition(key="from_int", range=m.Range(lte=t)),
                m.FieldCondition(key="to_int", range=m.Range(gte=t))])
            pts = self.client.query_points(self.COLLECTION, query=qv.tolist(), query_filter=flt,
                                           limit=k, with_payload=False).points
            ranked = [(p.id, p.score) for p in pts]
        else:
            sims = self.vecs @ qv
            ranked = sorted(((i, float(sims[i])) for i, c in enumerate(self.chunks)
                             if c["doc_id"] in allowed_ids), key=lambda x: -x[1])[:k]
        # Lớp phòng thủ thứ hai: loại mọi chunk không thuộc tập đã lọc bằng code.
        return [(i, s) for i, s in ranked if self.chunks[i]["doc_id"] in allowed_ids]

    def search(self, query: str, cond: dict, allowed_ids: set, k: int = 8) -> list:
        qv = embed([query], is_query=True)[0]
        dense = self._dense(qv, cond, allowed_ids, k * 2)
        pool = [(i, c) for i, c in enumerate(self.chunks) if c["doc_id"] in allowed_ids]
        sparse = [(pool[j][0], s) for j, s in bm25_rank(query, [c for _, c in pool])]
        fused = rrf([[i for i, _ in dense], [i for i, _ in sparse]])
        cos, bm = dict(dense), dict(sparse)
        top = sorted(fused, key=lambda i: -fused[i])[:k]
        return [{"chunk": self.chunks[i], "rrf": fused[i], "cos": cos.get(i), "bm25": bm.get(i)}
                for i in top]


# ---------- Hỗ trợ nhận diện chủ đề / đơn vị (bằng code)
SYNONYMS = {
    "nghỉ phép": ["phép năm", "ngày phép"],
    "làm thêm giờ": ["ot", "tăng ca", "overtime"],
    "công tác phí": ["công tác", "đi công tác"],
    "nghỉ lễ": ["quốc khánh", "ngày lễ", "nghỉ tết"],
    "bảo hiểm": ["bhyt"],
    "thưởng": ["bonus"],
    "tái cơ cấu": ["cắt giảm nhân sự"],
    "bảo mật": ["mật khẩu", "xác thực"],
}
STOP = set("của tôi như thế nào là có được bao nhiêu và cho về các một gì mấy không bạn em anh chị "
           "ở khi thì này đó quy định chính sách mình cần hỏi xin".split())


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def keyword_topics(question: str, topics: list) -> list:
    """Các chủ đề xuất hiện trong câu hỏi (khớp không dấu, theo ranh giới từ)."""
    q, hits = strip_accents(question), []
    for t in topics:
        for key in [t] + SYNONYMS.get(t, []):
            if re.search(r"\b" + re.escape(strip_accents(key)) + r"\b", q):
                hits.append(t)
                break
    return hits


def other_units(question: str, org: dict, user_unit: str) -> list:
    """Tên đơn vị KHÁC (không nằm trên đường đi của người hỏi) được nhắc trong câu hỏi."""
    mine, q = set(unit_path(user_unit)), question.lower()
    return [name for u, name in org.items() if u not in mine and name.lower() in q]


def coverage(question: str, text: str) -> float:
    """Tỷ lệ từ khóa của câu hỏi (bỏ từ dừng) xuất hiện trong đoạn."""
    q = [w for w in re.findall(r"\w+", question.lower()) if w not in STOP]
    if not q:
        return 0.0
    t = set(re.findall(r"\w+", text.lower()))
    return sum(w in t for w in q) / len(q)


# ============================================================ 4. PHÂN GIẢI XUNG ĐỘT
def depth(scope: str) -> int:
    return scope.count("/") + 1


def latest_versions(docs: list) -> list:
    """Cùng doc_key (nhiều phiên bản): giữ bản effective_from mới nhất."""
    best = {}
    for d in docs:
        k = d["doc_key"]
        if k not in best or d["effective_from"] > best[k]["effective_from"]:
            best[k] = d
    return list(best.values())


def resolve(allowed_docs: list, topic: str) -> dict:
    """Đầu vào: TẤT CẢ tài liệu đã lọc (không chỉ top-k) để không bỏ sót tài liệu 'floor' cấp trên."""
    res = {"status": "ok", "topic": topic, "primary": None, "floors": [], "additive": [],
           "superseded": [], "effective_params": {}, "warnings": [], "conflict_docs": []}
    docs = latest_versions([d for d in allowed_docs if d["topic"] == topic])
    if not docs:
        res["status"] = "empty"
        return res

    deepest = max(depth(d["scope"]) for d in docs)   # mọi tài liệu nằm trên 1 đường đi
    specific = [d for d in docs if depth(d["scope"]) == deepest]
    ancestors = [d for d in docs if depth(d["scope"]) < deepest]

    if len(specific) > 1:
        newest = max(d["effective_from"] for d in specific)
        top = [d for d in specific if d["effective_from"] == newest]
        if len(top) > 1:   # cùng cấp, cùng chủ đề, cùng ngày hiệu lực: không chọn bừa
            res["status"], res["conflict_docs"] = "conflict", top
            return res
        res["superseded"] += [d["id"] for d in specific if d not in top]
        res["warnings"].append(
            f"Có nhiều tài liệu cùng cấp về '{topic}'; dùng bản mới hơn ({top[0]['id']}).")
        specific = top
    primary = res["primary"] = specific[0]

    for a in ancestors:   # override_mode của tài liệu CẤP TRÊN quyết định cách kết hợp
        if a["override_mode"] == "override":
            res["superseded"].append(a["id"])
        elif a["override_mode"] == "floor":
            res["floors"].append(a)
        else:
            res["additive"].append(a)

    params = dict(primary.get("params", {}))
    for f in res["floors"]:
        for key, floor_val in f.get("params", {}).items():
            if key not in params:
                params[key] = floor_val
            elif params[key] < floor_val:
                res["warnings"].append(
                    f"{primary['id']} ghi {key}={params[key]} thấp hơn mức tối thiểu "
                    f"{floor_val} của {f['id']}; áp dụng {floor_val}, cần cảnh báo {primary['owner']}.")
                params[key] = floor_val
    res["effective_params"] = params
    return res