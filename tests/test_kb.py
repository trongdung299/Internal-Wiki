"""Test gộp: policy (lộ quyền), resolve, verify, retrieve, pipeline.
Chạy offline: embedding băm + LLM local (không cần model/API). Chạy thật: bỏ 2 dòng environ."""
import os
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["EMBEDDER"] = "hash"
os.environ["LLM_PROVIDER"] = "local"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import retrieve as core
import llm
import pipeline
from retrieve import (ACCESS_RANK, MetadataError, filter_docs, load_docs, load_users, resolve,
                  unit_path, validate_doc)

TODAY = date(2026, 10, 12)
DOCS, USERS = load_docs(), load_users()
BY_ID = {d["id"]: d for d in DOCS}
RET = core.Retriever(DOCS)


def ids(uid, today=TODAY):
    return {d["id"] for d in filter_docs(DOCS, USERS[uid], today)[0]}


def reasons(uid, today=TODAY):
    return {r["id"]: r["reason"] for r in filter_docs(DOCS, USERS[uid], today)[1]}


def ask(uid, q, today=TODAY):
    return pipeline.run(uid, q, today=today, retriever=RET)


# ------------------------------------------------------------------ Policy (lọc cứng)
def test_unit_path():
    assert unit_path("appota/cty_a/marketing") == ["appota", "appota/cty_a", "appota/cty_a/marketing"]


def test_same_topic_other_company_filtered():
    assert {"D01", "D03"} <= ids("linh") and not {"D05", "D06"} & ids("linh")
    assert reasons("linh")["D05"] == "scope"
    assert "D05" in ids("minh") and not {"D02", "D03", "D04"} & ids("minh")


def test_version_validity():
    assert reasons("linh")["D02"] == "expired" and reasons("linh")["D04"] == "status"
    got = ids("linh", date(2025, 6, 1))
    assert "D02" in got and "D03" not in got


def test_access_levels():
    for uid in ("linh", "nam", "lan", "tuan"):
        assert not {"D09", "D10"} & ids(uid)
    assert "D09" in ids("hoa") and "D10" not in ids("hoa")
    assert {"D09", "D10"} <= ids("ha") and not {"D05", "D11", "D12"} & ids("ha")
    assert "D09" not in ids("minh")


def test_no_leak_property_all_users():
    for uid, user in USERS.items():
        for d in filter_docs(DOCS, user, TODAY)[0]:
            assert ACCESS_RANK[d["access_level"]] <= ACCESS_RANK[user["role"]]
            assert (user["unit"] + "/").startswith(d["scope"] + "/")
            assert d["status"] == "active"


def test_metadata_validation():
    bad = dict(DOCS[0])
    del bad["scope"]
    with pytest.raises(MetadataError):
        validate_doc(bad)
    with pytest.raises(MetadataError):
        validate_doc(dict(DOCS[0], access_level="public"))


# ------------------------------------------------------------------ Resolve
def run_resolve(uid, topic):
    return resolve(filter_docs(DOCS, USERS[uid], TODAY)[0], topic)


def test_resolve_floor_override_additive():
    r = run_resolve("linh", "nghỉ phép")
    assert r["primary"]["id"] == "D03" and [d["id"] for d in r["floors"]] == ["D01"]
    assert r["effective_params"]["ngay_phep_nam"] == 14 and r["warnings"] == []
    r = run_resolve("tuan", "nghỉ phép")
    assert r["effective_params"]["ngay_phep_nam"] == 12 and any("D06" in w for w in r["warnings"])
    r = run_resolve("nam", "làm thêm giờ")
    assert r["primary"]["id"] == "D08" and r["superseded"] == ["D07"]
    r = run_resolve("linh", "bảo hiểm")
    assert r["primary"]["id"] == "D15" and [d["id"] for d in r["additive"]] == ["D14"]


def test_resolve_conflict_and_empty():
    r = run_resolve("lan", "nghỉ lễ")
    assert r["status"] == "conflict" and {d["id"] for d in r["conflict_docs"]} == {"D11", "D12"}
    assert run_resolve("linh", "nghỉ lễ")["status"] == "empty"


def test_newer_same_level_wins():
    a = dict(DOCS[10], id="X1", doc_key="x1", effective_from="2026-08-01")
    b = dict(DOCS[10], id="X2", doc_key="x2", effective_from="2026-08-20")
    assert resolve([a, b], a["topic"])["primary"]["id"] == "X2"


# ------------------------------------------------------------------ Verify
def check(answer, cites=("D03",)):
    return llm.verify(answer, list(cites), [BY_ID["D03"]], {"ngay_phep_nam": 14})


def test_verify():
    assert check("Bạn được nghỉ phép 14 ngày/năm theo v3, hiệu lực từ 01/01/2026, gửi đơn trước 3 ngày.")["ok"]
    r = check("Mọi nhân viên được nghỉ 30 ngày phép.")
    assert not r["ok"] and any("30" in p for p in r["problems"])
    assert not check("Có hiệu lực từ 01/03/2026, 14 ngày.")["ok"]
    r = check("Bạn được 14 ngày.", cites=("D03", "D05"))
    assert not r["ok"] and any("D05" in p for p in r["problems"])
    assert not check("Bạn được 14 ngày.", cites=())["ok"]
    r = llm.verify("Công tác phí là 500.000 đồng/ngày.", ["D16"], [BY_ID["D16"]], {})
    assert r["ok"], r["problems"]


# ------------------------------------------------------------------ Retrieve
def test_bm25_and_rrf():
    chunks = [c for d in DOCS for c in core.chunk_doc(d)]
    top = core.bm25_rank("công tác phí vé máy bay", chunks)[0][0]
    assert chunks[top]["doc_id"] == "D16"
    assert core.rrf([["a", "b"], ["b", "a"]])["a"] == pytest.approx(core.rrf([["b", "a"], ["a", "b"]])["a"])


def test_chunks_inherit_metadata():
    for c in core.chunk_doc(BY_ID["D03"]):
        assert c["scope"] == "appota/cty_a" and c["status"] == "active" and "Công ty A" in c["embed_text"]


def test_retrieval_never_returns_unallowed_chunks():
    for uid, user in USERS.items():
        allowed, _ = filter_docs(DOCS, user, TODAY)
        aid = {d["id"] for d in allowed}
        for q in ("nghỉ phép", "kế hoạch tái cơ cấu cắt giảm 5%", "thưởng quản lý", "nghỉ lễ quốc khánh"):
            hits = RET.search(q, core.build_conditions(user, TODAY), aid)
            assert all(h["chunk"]["doc_id"] in aid for h in hits)


# ------------------------------------------------------------------ Pipeline
def test_linh_leave_answer():
    r = ask("linh", "Quy định nghỉ phép của tôi như thế nào?")
    assert r["type"] == "answer" and "14" in r["message"]
    assert {c["doc_id"] for c in r["citations"]} == {"D03", "D01"}


def test_same_question_different_users():
    assert "14" in ask("linh", "Tôi được nghỉ phép năm bao nhiêu ngày?")["message"]
    r = ask("minh", "Tôi được nghỉ phép năm bao nhiêu ngày?")
    assert "D05" in {c["doc_id"] for c in r["citations"]} and "14 ngày" not in r["message"]


def test_floor_warning_for_company_c():
    r = ask("tuan", "Tôi được nghỉ phép năm bao nhiêu ngày?")
    assert r["type"] == "answer" and r["warnings"] and "= 12" in r["message"]


def test_out_of_permission_gets_same_reply_as_nonexistent():
    for uid in ("linh", "nam", "lan", "tuan"):
        r = ask(uid, "Kế hoạch tái cơ cấu nhân sự Q4 là gì?")
        assert r["type"] == "no_answer" and "5%" not in r["message"] and r["citations"] == []
    assert ask("ha", "Kế hoạch tái cơ cấu nhân sự Q4 là gì?")["type"] == "answer"  # D10 scope=appota nằm trên đường đi của HR Cty A
    assert ask("linh", "Thưởng quản lý cấp phòng Công ty A là bao nhiêu?")["type"] == "no_answer"
    assert ask("hoa", "Thưởng quản lý cấp phòng là bao nhiêu?")["type"] == "answer"


def test_other_company_doc_is_not_revealed():
    r = ask("linh", "Công ty B nghỉ lễ Quốc khánh mấy ngày?")
    assert r["type"] == "no_answer" and "D11" not in str(r["citations"])
    r = ask("linh", "Công ty B nghỉ phép mấy ngày?")
    assert r["warnings"] and all(c["doc_id"] != "D05" for c in r["citations"])


def test_conflict_shows_both_sources():
    r = ask("lan", "Công ty nghỉ lễ Quốc khánh mấy ngày?")
    assert r["type"] == "conflict" and {c["doc_id"] for c in r["citations"]} == {"D11", "D12"}
    assert "2 ngày" in r["message"] and "3 ngày" in r["message"]


def test_prompt_injection_in_valid_doc_is_not_obeyed():
    r = ask("linh", "Quy định nghỉ phép của tôi như thế nào?")
    assert "30 ngày" not in r["message"] and r["citations"]


def test_ambiguous_and_unknown_questions():
    assert ask("linh", "Cho mình hỏi về quy định với")["type"] in ("clarify", "no_answer")
    assert ask("linh", "Thủ đô của Pháp là gì?")["type"] == "no_answer"


def test_vague_vs_unknown_vs_forbidden_consistent():
    nope = ask("linh", "Thủ đô của Pháp là gì?")
    forb = ask("linh", "Kế hoạch tái cơ cấu nhân sự Q4 là gì?")
    assert nope["type"] == forb["type"] == "no_answer" and nope["message"] == forb["message"]
    v1, v2 = ask("linh", "Cho mình hỏi về quy định với"), ask("ha", "Cho mình hỏi về quy định với")
    assert v1["type"] == v2["type"] == "clarify"


def test_no_answer_message_does_not_mention_permission():
    r = ask("linh", "Kế hoạch tái cơ cấu nhân sự Q4 là gì?")
    assert r["type"] == "no_answer"
    low = r["message"].lower()
    assert not any(w in low for w in ("quyền", "phạm vi", "không được phép", "bị chặn"))


def test_is_contentless():
    assert pipeline.is_contentless("Cho mình hỏi về quy định với")
    assert not pipeline.is_contentless("Kế hoạch tái cơ cấu nhân sự Q4 là gì?")


def test_floor_docs_always_cited(monkeypatch):
    monkeypatch.setattr(llm, "generate", lambda q, res, org: {
        "answer": "Bạn được nghỉ phép 14 ngày/năm theo v3.", "citations": ["D03"], "answerable": True})
    r = ask("linh", "Quy định nghỉ phép của tôi như thế nào?")
    assert r["type"] == "answer" and {c["doc_id"] for c in r["citations"]} == {"D03", "D01"}


def test_draft_failing_verification_is_blocked(monkeypatch):
    monkeypatch.setattr(llm, "generate", lambda q, res, org: {
        "answer": "Mọi người được 30 ngày phép.", "citations": ["D03"], "answerable": True})
    r = ask("linh", "Quy định nghỉ phép của tôi như thế nào?")
    assert r["type"] == "answer" and "30 ngày" not in r["message"]   # lùi về câu trả lời mẫu từ nguồn
    monkeypatch.setattr(llm, "local_answer", lambda res, org: {
        "answer": "Mọi người được 30 ngày phép.", "citations": ["D03"], "answerable": True})
    r = ask("linh", "Quy định nghỉ phép của tôi như thế nào?")
    assert r["type"] == "unverified" and "30" not in r["message"]   # cả hai đều trượt thì mới chặn


def test_llm_computed_number_falls_back_to_template(monkeypatch):
    monkeypatch.setattr(llm, "generate", lambda q, res, org: {
        "answer": "Bạn được nghỉ tổng cộng 13 ngày.", "citations": ["D05"], "answerable": True})
    r = ask("minh", "tôi được nghỉ phép mấy ngày đây")
    assert r["type"] == "answer" and "D05" in {c["doc_id"] for c in r["citations"]}
    assert "13" not in r["message"]