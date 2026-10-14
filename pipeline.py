"""Luồng xử lý 6 bước theo kế hoạch + CLI.

  1. Lấy hồ sơ người dùng  2. Lọc cứng bằng code  3. Tìm kiếm hybrid (BM25 + bge-m3, RRF)
  4. Giải xung đột bằng quy tắc  5. LLM trả lời có trích dẫn  6. Code kiểm tra bám nguồn
Không đủ căn cứ / còn mâu thuẫn / không bám nguồn  =>  nói rõ chưa chắc, chuyển owner/HR.

CLI: python pipeline.py --user linh "Quy định nghỉ phép của tôi như thế nào?" [--debug]
"""
import argparse
import re
import sys
from collections import defaultdict
from datetime import date

import config
import retrieve as core
import llm

TOP_K_TOPIC = 5
# Từ "rỗng" trong câu hỏi tra cứu. Còn < 2 từ có nội dung => câu hỏi không có chủ thể.
_FILLER = set("""cho mình tôi em anh chị bạn hỏi về với là gì của như thế nào không có được bao nhiêu
mấy xin ạ nhé thì và các những một quy định chính sách thông tin cái nào đó ơi vậy""".split())
_RETRIEVER = None


def get_retriever(docs: list) -> core.Retriever:
    global _RETRIEVER
    if _RETRIEVER is None:
        _RETRIEVER = core.Retriever(docs)
    return _RETRIEVER


def is_contentless(question: str) -> bool:
    toks = re.findall(r"\w+", question.lower())
    return len([t for t in toks if t not in _FILLER]) < 2


def topic_from_hits(question: str, hits: list):
    """Khi phân tích câu hỏi chưa ra chủ đề: lấy chủ đề từ kết quả truy xuất.
    Trả về (topic | None, 'ambiguous' | 'no_evidence' | None)."""
    if not hits:
        return None, "no_evidence"
    score = defaultdict(float)
    for h in hits[:TOP_K_TOPIC]:
        score[h["chunk"]["topic"]] += h["rrf"]
    ranked = sorted(score.items(), key=lambda x: -x[1])
    best_topic = ranked[0][0]
    best_hit = next(h for h in hits if h["chunk"]["topic"] == best_topic)
    if core.coverage(question, best_hit["chunk"]["text"]) < config.coverage_min():
        return None, "no_evidence"
    if len(ranked) > 1 and ranked[1][1] >= config.ambiguity_ratio() * ranked[0][1]:
        return None, "ambiguous"
    return best_topic, None


def run(user_id: str, question: str, today: date = None, retriever=None) -> dict:
    today = today or date.today()
    # 1. Hồ sơ người dùng (đọc lại mỗi lần = real-time)
    user = core.load_users()[user_id]
    org = core.load_org()
    docs = core.load_docs()
    # 2. Lọc cứng bằng code, trước khi AI hoặc truy xuất nhìn thấy dữ liệu
    cond = core.build_conditions(user, today)
    allowed, rejected = core.filter_docs(docs, user, today)
    allowed_ids = {d["id"] for d in allowed}
    topics = sorted({d["topic"] for d in allowed})
    dbg = {"allowed_ids": sorted(allowed_ids), "rejected": rejected, "topics": topics}

    def out(type_, message, citations=None, warnings=None):
        return {"type": type_, "message": message, "citations": citations or [],
                "warnings": warnings or [], "debug": dbg}

    # Câu từ chối phải trung tính: không nhắc quyền/phạm vi, để không lộ là có tài liệu tồn tại.
    NO_ANSWER = ("Mình chưa tìm thấy thông tin phù hợp với câu hỏi này nên không dám đoán. "
                 "Bạn thử diễn đạt lại câu hỏi, hoặc hỏi trực tiếp HR.")

    def clarify(ask=None):
        return out("clarify", ask or ("Câu hỏi chưa đủ rõ. Bạn muốn hỏi về chủ đề nào: "
                                       + ", ".join(topics) + "?"), warnings=warnings)

    # Phân tích câu hỏi (AI chỉ nhận chủ đề trong quyền người hỏi)
    analysis = llm.analyze(question, topics, org)
    dbg["analysis"] = analysis
    warnings = []
    if analysis["other_unit"] or core.other_units(question, org, user["unit"]):
        warnings.append("Bạn đang nhắc đến đơn vị khác. Hệ thống chỉ tra cứu theo đơn vị của "
                        f"bạn ({org.get(user['unit'], user['unit'])}); hãy hỏi đơn vị đó để biết quy định riêng.")
    # Chỉ hỏi lại khi câu hỏi thật sự không có chủ thể. Cờ mo_ho của LLM không đủ để hỏi lại,
    # vì LLM chỉ thấy chủ đề trong quyền nên câu hỏi về chủ đề ngoài quyền cũng bị gắn "mơ hồ".
    if is_contentless(question):
        return clarify(analysis["ask_back"])

    # 3. Tìm kiếm hybrid trong tập đã lọc
    ret = retriever or get_retriever(docs)
    hits = ret.search(question, cond, allowed_ids)
    dbg["retrieval"] = {"backend": ret.backend,
                        "hits": [(h["chunk"]["chunk_id"], round(h["rrf"], 4)) for h in hits]}

    topic = analysis["topic"]
    if not topic:
        forbidden = [t for t in core.keyword_topics(question, sorted({d["topic"] for d in docs}))
                     if t not in topics]
        if forbidden:   # chủ đề có trong kho nhưng ngoài quyền: trả lời y hệt "không có", không lộ gì
            return out("no_answer", NO_ANSWER, warnings=warnings)
        topic, why = topic_from_hits(question, hits)
        if why == "ambiguous":
            return clarify()
        if why:
            return out("no_answer", NO_ANSWER, warnings=warnings)
    dbg["topic"] = topic

    # 4. Giải xung đột bằng quy tắc
    res = core.resolve(allowed, topic)
    dbg["resolve"] = {k: res[k] for k in ("status", "superseded", "effective_params", "warnings")}
    if res["status"] == "empty":
        return out("no_answer", NO_ANSWER, warnings=warnings)
    if res["status"] == "conflict":
        cds = res["conflict_docs"]
        lines = [f"- {d['title']} (hiệu lực từ {llm.fmt_date(d['effective_from'])}, "
                 f"người phụ trách: {d['owner']}): {d['content']}" for d in cds]
        msg = ("Có hai tài liệu cùng cấp, cùng ngày hiệu lực nhưng nội dung khác nhau nên mình không "
               "chọn bừa:\n" + "\n".join(lines) + "\nĐã chuyển cấp trên/người phụ trách xử lý, "
               "vui lòng xác nhận trực tiếp.")
        return out("conflict", msg, [llm.citation(d, org) for d in cds], warnings)

    # 5. LLM trả lời có trích dẫn
    docs_sel = [d for d, _ in llm.selected_docs(res)]
    draft = llm.generate(question, res, org)
    dbg["draft_note"] = draft.get("note")
    if not draft["answerable"]:
        return out("no_answer", NO_ANSWER, warnings=warnings)

    # 6. Code đối chiếu số/ngày/trích dẫn với đoạn nguồn
    check = llm.verify(draft["answer"], draft["citations"], docs_sel, res["effective_params"])
    dbg["verify"] = check
    if not check["ok"]:
        # LLM viết lệch nguồn (ví dụ tự cộng số): lùi về câu trả lời mẫu dựng từ nguồn, vẫn phải qua verify
        dbg["draft_rejected"] = draft["answer"]
        fallback = llm.local_answer(res, org)
        check_fb = llm.verify(fallback["answer"], fallback["citations"], docs_sel, res["effective_params"])
        if check_fb["ok"]:
            draft, check = fallback, check_fb
            dbg["verify_fallback"] = "local_answer"
    if not check["ok"]:
        owner = res["primary"]["owner"]
        return out("unverified", "Mình chưa thể xác nhận câu trả lời bám đúng tài liệu nguồn nên không "
                   f"đưa ra để tránh sai lệch. Vui lòng hỏi trực tiếp {owner}.", warnings=warnings)
    # Tài liệu mức tối thiểu/bổ sung góp vào mức áp dụng nên code luôn gắn vào căn cứ, không tin LLM nhớ cite
    must = {d["id"] for d, role in llm.selected_docs(res) if role != "chinh"}
    cited = [d for d in docs_sel if d["id"] in set(draft["citations"]) | must]
    return out("answer", draft["answer"], [llm.citation(d, org) for d in cited],
               warnings + res["warnings"])


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?")
    ap.add_argument("--user", default="linh")
    ap.add_argument("--today", help="YYYY-MM-DD (mặc định: hôm nay)")
    ap.add_argument("--debug", action="store_true", help="in tài liệu bị loại (chỉ dùng nội bộ)")
    a = ap.parse_args()
    users = core.load_users()
    if not a.question:
        for u in users.values():
            print(f"{u['id']:6} {u['name']:22} {u['unit']:34} {u['role']}")
        return
    r = run(a.user, a.question, today=date.fromisoformat(a.today) if a.today else None)
    u = users[a.user]
    print(f"[{u['name']} | {u['unit']} | {u['role']} | LLM: {config.provider()}]")
    print(f"Loại phản hồi: {r['type']}\n\n{r['message']}")
    if r["warnings"]:
        print("\nCảnh báo:", *r["warnings"], sep="\n - ")
    if r["citations"]:
        print("\nCăn cứ:")
        for c in r["citations"]:
            print(f" - {c['title']} | {c['version']} | hiệu lực từ "
                  f"{llm.fmt_date(c['effective_from'])} | {c['scope_name']} ({c['doc_id']})")
    if a.debug:
        print("\n--- DEBUG (không hiển thị cho người dùng) ---")
        for k, v in r["debug"].items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()