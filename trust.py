"""Lớp tin cậy (Mission 3), bọc ngoài pipeline.run mà không sửa pipeline.

Làm 5 việc, mỗi việc ứng với một yêu cầu cải tiến chung:
  1. Mốc thời gian trong câu hỏi ("năm 2025", "tháng 3/2026", "15/01/2026", "năm ngoái") được
     đọc thành NGÀY TRA CỨU. Chỉ ảnh hưởng phần hiệu lực; quyền và đơn vị vẫn lấy từ hồ sơ.
  2. Nhật ký truy cập (logs/access_log.jsonl): mỗi lần hỏi ghi người hỏi, loại phản hồi, nguồn.
  3. Giải thích vì sao quy định cấp trên bị thay thế / làm mức tối thiểu / bổ sung.
  4. Khi không có quy định hiệu lực tại mốc được hỏi: nói rõ mốc và bản sớm nhất có hiệu lực.
  5. Bằng chứng để người dùng kiểm chứng: đoạn trích NGUYÊN VĂN từ tài liệu (đánh dấu câu chứa
     số liệu có trong câu trả lời) và lịch sử phiên bản của cùng tài liệu.
Ngoài ra báo rõ khi Gemini lỗi và hệ thống đang chạy chế độ dự phòng.
"""
import calendar
import json
import re
from datetime import date, datetime, timedelta

import config
import pipeline
import retrieve

# ------------------------------------------------------------------ 1. Mốc thời gian
_FULL_VN = re.compile(r"ngay\s*(\d{1,2})\s*thang\s*(\d{1,2})(?:\s*nam)?\s*(\d{4})")
_FULL = re.compile(r"(?<!\d)(\d{1,2})\s*[/-]\s*(\d{1,2})\s*[/-]\s*(\d{4})(?!\d)")
_MONTH = re.compile(r"thang\s*(\d{1,2})\s*(?:/|-|nam)?\s*(\d{4})")
_MONTH_SLASH = re.compile(r"(?<![\d/])(\d{1,2})\s*/\s*(\d{4})(?!\d)")
_MONTH_REL = re.compile(r"thang\s*(\d{1,2})\s*nam\s*(nay|ngoai|truoc)")
_YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
_LAST_YEAR = re.compile(r"nam\s+(ngoai|truoc)")
_LAST_MONTH = re.compile(r"thang\s+truoc")


def fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def parse_as_of(question: str, today: date):
    """Trả về (ngày_tra_cứu, ghi_chú | None). Không có mốc thì trả về (today, None).
    Mốc trong quá khứ -> dùng ngày cuối của kỳ đó (bản mới nhất còn hiệu lực trong kỳ).
    Mốc đang diễn ra hoặc ở tương lai -> dùng hôm nay (bản dự thảo/chưa hiệu lực không được tính)."""
    q = retrieve.strip_accents(question)
    cands, future = [], []

    def add(start: date, end: date, label: str):
        if start > today:
            future.append(label)
        elif end < today:
            cands.append((end, label))

    def scan(rx, build):
        nonlocal q
        for m in list(rx.finditer(q)):
            try:
                build(m)
            except ValueError:      # ngày không tồn tại, ví dụ 31/02: bỏ qua nhưng vẫn không để rơi sang "năm"
                pass
            q = q[:m.start()] + " " * (m.end() - m.start()) + q[m.end():]

    def day(m):
        d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        add(d, d, fmt(d))

    def month(m, mo=1, yr=2):
        mm, yy = int(m.group(mo)), int(m.group(yr))
        add(date(yy, mm, 1), _month_end(yy, mm), f"tháng {mm}/{yy}")

    def month_rel(m):
        mm = int(m.group(1))
        yy = today.year if m.group(2) == "nay" else today.year - 1
        add(date(yy, mm, 1), _month_end(yy, mm), f"tháng {mm} năm {'nay' if yy == today.year else 'ngoái'} ({mm}/{yy})")

    def year(m):
        y = int(m.group(1))
        add(date(y, 1, 1), date(y, 12, 31), f"năm {y}")

    scan(_FULL_VN, day)
    scan(_FULL, day)
    scan(_MONTH, month)
    scan(_MONTH_SLASH, month)
    scan(_MONTH_REL, month_rel)
    scan(_YEAR, year)
    if _LAST_YEAR.search(q):
        y = today.year - 1
        add(date(y, 1, 1), date(y, 12, 31), f"năm ngoái ({y})")
    if _LAST_MONTH.search(q):
        first = today.replace(day=1)
        prev_end = first - timedelta(days=1)
        add(prev_end.replace(day=1), prev_end, f"tháng trước ({prev_end.month}/{prev_end.year})")

    if cands:
        as_of, label = max(cands)
        note = f"Tra cứu theo hiệu lực tại {fmt(as_of)} (theo mốc '{label}' trong câu hỏi)."
        if len(cands) > 1:
            note += " Câu hỏi có nhiều mốc thời gian, hệ thống dùng mốc muộn nhất."
        return as_of, note
    if future:
        return today, (f"Mốc '{future[0]}' ở tương lai: hệ thống dùng quy định đang có hiệu lực hôm nay "
                       f"({fmt(today)}); bản dự thảo hoặc chưa hiệu lực không được tính.")
    return today, None


# ------------------------------------------------------------------ 3, 5. Bằng chứng
def _sentences(text: str) -> list:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def _nums(text: str) -> set:
    return {re.sub(r"[.,]", "", n) for n in re.findall(r"\d+(?:[.,]\d+)*", text)}


def _perm_ok(d: dict, user: dict) -> bool:
    """Quyền + đơn vị (không xét thời gian/trạng thái)."""
    return (retrieve.ACCESS_RANK[d["access_level"]] <= retrieve.ACCESS_RANK[user["role"]]
            and d["scope"] in retrieve.unit_path(user["unit"]))


def _history(doc: dict, docs: list, user: dict, as_of: date) -> list:
    """Các phiên bản đã ban hành của cùng tài liệu mà người hỏi được phép xem.
    Không hiện bản nháp/thu hồi (chưa ban hành hoặc đã hủy)."""
    out = []
    for d in sorted(docs, key=lambda x: x["effective_from"]):
        if d["doc_key"] != doc["doc_key"] or d["status"] != "active" or not _perm_ok(d, user):
            continue
        frm = date.fromisoformat(d["effective_from"])
        to = date.fromisoformat(d["effective_to"]) if d.get("effective_to") else None
        if frm > as_of:
            state = "chưa có hiệu lực"
        elif to and to < as_of:
            state = "đã hết hiệu lực"
        else:
            state = "đang áp dụng"
        out.append({"doc_id": d["id"], "version": d["version"], "effective_from": d["effective_from"],
                    "effective_to": d.get("effective_to"), "state": state})
    return out


def build_evidence(user: dict, docs: list, as_of: date, result: dict) -> list:
    by_id = {d["id"]: d for d in docs}
    answer_nums = _nums(result["message"])
    ev = []
    for c in result["citations"]:
        d = by_id.get(c["doc_id"])
        if not d:
            continue
        quote = [{"text": s, "highlight": bool(_nums(s) & answer_nums)} for s in _sentences(d["content"])]
        ev.append({"doc_id": d["id"], "title": d["title"], "version": d["version"],
                   "effective_from": d["effective_from"], "effective_to": d.get("effective_to"),
                   "scope": d["scope"], "owner": d["owner"], "quote": quote,
                   "history": _history(d, docs, user, as_of)})
    return ev


def explain_hierarchy(user: dict, docs: list, as_of: date, result: dict, org: dict) -> list:
    """Giải thích bằng lời quy định nào được dùng, quy định nào bị thay thế / làm sàn / bổ sung."""
    if not result["citations"]:
        return []
    by_id = {d["id"]: d for d in docs}
    first = by_id.get(result["citations"][0]["doc_id"])
    if not first:
        return []
    allowed = retrieve.filter_docs(docs, user, as_of)[0]
    res = retrieve.resolve(allowed, first["topic"])
    p = res.get("primary")
    if not p:
        return []
    unit = lambda d: org.get(d["scope"], d["scope"])
    lines = []
    for sid in res["superseded"]:
        s = by_id.get(sid)
        if not s:
            continue
        if s["scope"] == p["scope"]:
            lines.append(f"{s['id']} ({s['title']}, {s['version']}) là bản cũ hơn cùng cấp nên "
                         f"được thay bằng {p['id']} ({p['version']}).")
        else:
            lines.append(f"{s['id']} ({s['title']}, {unit(s)}) không được áp dụng vì {p['id']} "
                         f"({p['title']}, {unit(p)}) cụ thể hơn và thay thế (override).")
    for f in res["floors"]:
        lines.append(f"{f['id']} ({f['title']}, {unit(f)}) đặt mức tối thiểu: {p['id']} "
                     "không được ghi thấp hơn mức này.")
    for a in res["additive"]:
        lines.append(f"{a['id']} ({a['title']}, {unit(a)}) được áp dụng bổ sung cùng {p['id']}.")
    return lines


# ------------------------------------------------------------------ 4. Không có quy định tại mốc
def no_valid_at_date(user: dict, docs: list, question: str, as_of: date):
    """Câu giải thích cụ thể khi người hỏi có quyền với chủ đề nhưng không có bản nào hiệu lực tại mốc."""
    perm = [d for d in docs if d["status"] == "active" and _perm_ok(d, user)]
    cond = retrieve.build_conditions(user, as_of)
    for t in retrieve.keyword_topics(question, sorted({d["topic"] for d in perm})):
        ds = [d for d in perm if d["topic"] == t]
        if any(retrieve.check_doc(d, cond)[0] for d in ds):
            continue
        earliest = min(ds, key=lambda d: d["effective_from"])
        if earliest["effective_from"] > as_of.isoformat():
            return (f"Không có quy định về '{t}' của đơn vị bạn có hiệu lực tại {fmt(as_of)}. "
                    f"Bản sớm nhất có hiệu lực từ {fmt(date.fromisoformat(earliest['effective_from']))} "
                    f"({earliest['title']}, {earliest['version']}). Mình không đoán quy định trước thời điểm đó.")
        return (f"Không có quy định về '{t}' của đơn vị bạn còn hiệu lực tại {fmt(as_of)}. "
                "Vui lòng liên hệ HR hoặc quản trị đơn vị của bạn.")
    return None


# ------------------------------------------------------------------ 2. Nhật ký truy cập
def audit(user: dict, question: str, as_of: date, result: dict) -> None:
    if config.get("AUDIT_LOG", "1") == "0":
        return
    rej = result.get("debug", {}).get("rejected", [])
    entry = {"ts": datetime.now().isoformat(timespec="seconds"), "user": user["id"], "unit": user["unit"],
             "role": user["role"], "question": question, "as_of": as_of.isoformat(),
             "type": result["type"], "cited": [c["doc_id"] for c in result["citations"]],
             "blocked_by_permission": sum(1 for r in rej if r.get("reason") in ("access", "scope")),
             "degraded": result.get("degraded", False)}
    try:        # ghi log không bao giờ được làm hỏng câu trả lời (ví dụ máy chủ không cho ghi file)
        p = config.ROOT / "logs" / "access_log.jsonl"
        p.parent.mkdir(exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ------------------------------------------------------------------ Điểm vào chính
def ask(user_id: str, question: str, today: date = None, retriever=None, audit_log: bool = True) -> dict:
    real_today = today or date.today()
    as_of, time_note = parse_as_of(question, real_today)
    kw = {"retriever": retriever} if retriever is not None else {}
    r = dict(pipeline.run(user_id, question, today=as_of, **kw))

    user, docs, org = retrieve.load_users()[user_id], retrieve.load_docs(), retrieve.load_org()
    r["as_of"], r["time_note"] = as_of.isoformat(), time_note
    if r["type"] in ("no_answer", "denied") and as_of != real_today:
        msg = no_valid_at_date(user, docs, question, as_of)
        if msg:
            r["message"], r["reason"] = msg, "no_valid_version_at_date"
    if r["type"] == "answer":
        topics = sorted({d["topic"] for d in retrieve.filter_docs(docs, user, as_of)[0]})
        found = retrieve.keyword_topics(question, topics)
        if len(found) >= 2:     # tránh trả lời một chủ đề rồi lặng lẽ bỏ qua chủ đề còn lại
            r["type"], r["reason"] = "clarify", "multi_topic"
            r["message"] = (f"Câu hỏi của bạn có {len(found)} chủ đề: {', '.join(found)}. Để không bỏ sót hay "
                            "lẫn số liệu, bạn muốn hỏi chủ đề nào trước? Mình sẽ trả lời từng chủ đề.")
            r["citations"], r["warnings"] = [], []
    r["evidence"] = build_evidence(user, docs, as_of, r) if r["type"] in ("answer", "conflict") else []
    r["explanations"] = explain_hierarchy(user, docs, as_of, r, org) if r["type"] == "answer" else []

    dbg = r.get("debug", {})
    r["degraded"] = config.provider() == "gemini" and (
        dbg.get("analysis", {}).get("source") == "local" or bool(dbg.get("draft_note")))
    r["notice"] = ("Gemini tạm thời không khả dụng: câu trả lời được dựng từ tài liệu gốc theo mẫu "
                   "(vẫn kiểm tra nguồn) nên có thể kém tự nhiên, hoặc từ chối nhầm câu diễn đạt đời thường."
                   if r["degraded"] else None)
    if audit_log:
        audit(user, question, as_of, r)
    return r