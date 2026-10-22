"""Giao diện demo: streamlit run app.py"""
import html
from datetime import date

import streamlit as st

import retrieve
import trust

st.set_page_config(page_title="Tri thức nội bộ Appota", page_icon="📘", layout="centered")

st.markdown("""
<style>
.card{border:1px solid rgba(128,128,128,.28);border-left:6px solid var(--c);border-radius:10px;
      padding:14px 18px;margin:10px 0 6px 0;background:rgba(128,128,128,.06)}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.78rem;font-weight:600;
       color:var(--c);background:color-mix(in srgb,var(--c) 15%,transparent);margin-bottom:8px}
.msg{font-size:1.02rem;line-height:1.6}
.src{border:1px solid rgba(128,128,128,.28);border-radius:10px;padding:12px 16px;margin:8px 0}
.src b{font-size:.98rem}
.chip{display:inline-block;padding:1px 9px;margin:4px 6px 0 0;border-radius:999px;font-size:.76rem;
      background:rgba(128,128,128,.16)}
.quote{border-left:3px solid rgba(128,128,128,.4);padding:2px 12px;margin:8px 0;font-size:.93rem;line-height:1.55}
.quote mark{background:rgba(255,200,0,.35);color:inherit;padding:0 2px;border-radius:3px}
.me{border:1px solid rgba(128,128,128,.28);border-radius:10px;padding:10px 12px;font-size:.9rem}
</style>
""", unsafe_allow_html=True)

TYPES = {
    "answer": ("✅", "Câu trả lời", "#16a34a"),
    "conflict": ("⚠️", "Có thông tin mâu thuẫn", "#d97706"),
    "clarify": ("💬", "Cần làm rõ câu hỏi", "#2563eb"),
    "denied": ("🔒", "Ngoài quyền hoặc không có thông tin", "#6b7280"),
    "no_answer": ("🔒", "Không có thông tin phù hợp", "#6b7280"),
    "unverified": ("🛡️", "Chưa xác nhận được nguồn", "#dc2626"),
}
EXAMPLES = [
    "Quy định nghỉ phép của tôi như thế nào?",
    "Năm 2025 tôi được nghỉ phép bao nhiêu ngày?",
    "Làm thêm giờ ngày thường được trả bao nhiêu?",
    "Phúc lợi bảo hiểm của tôi gồm những gì?",
    "Công ty sẽ nghỉ lễ Quốc khánh mấy ngày?",
    "Kế hoạch tái cơ cấu nhân sự là gì?",
]
ROLE_VN = {"staff": "Nhân viên", "manager": "Quản lý", "hr": "HR"}


def esc(s) -> str:
    return html.escape(str(s)).replace("\n", "<br>")


def dmy(iso) -> str:
    return "nay" if not iso else date.fromisoformat(iso).strftime("%d/%m/%Y")


def set_question(text: str):
    st.session_state.q = text
    st.session_state.go = True


def trigger():
    st.session_state.go = True


# ------------------------------------------------------------------ Sidebar
users, org = retrieve.load_users(), retrieve.load_org()
uid = st.sidebar.selectbox("Đăng nhập (giả lập)", list(users),
                           format_func=lambda i: f"{users[i]['name']} · {ROLE_VN[users[i]['role']]}")
u = users[uid]
path = " › ".join(org.get(p, p) for p in retrieve.unit_path(u["unit"]))
st.sidebar.markdown(f"<div class='me'><b>{esc(u['name'])}</b><br>{ROLE_VN[u['role']]}<br>"
                    f"<span style='opacity:.75'>{esc(path)}</span></div>", unsafe_allow_html=True)
st.sidebar.caption("Hồ sơ lấy từ hệ thống xác thực, không lấy từ câu hỏi.")
today = st.sidebar.date_input("Ngày tra cứu", date.today(),
                              help="Câu hỏi có mốc thời gian (ví dụ 'năm 2025') sẽ ghi đè ngày này.")
debug = st.sidebar.checkbox("Chế độ debug (chỉ nội bộ)")

# ------------------------------------------------------------------ Trang chính
st.title("📘 Tra cứu quy định nội bộ")
st.caption("Đúng đơn vị · đúng quyền · đúng phiên bản · luôn kèm căn cứ để kiểm chứng")

st.text_input("Câu hỏi", key="q", on_change=trigger, placeholder="Ví dụ: Quy định nghỉ phép của tôi như thế nào?")
st.button("Tra cứu", type="primary", on_click=trigger)
st.caption("Thử nhanh:")
cols = st.columns(2)
for i, ex in enumerate(EXAMPLES):
    cols[i % 2].button(ex, key=f"ex{i}", on_click=set_question, args=(ex,), use_container_width=True)

run = st.session_state.pop("go", False)
if run and st.session_state.get("q", "").strip():
    with st.spinner("Đang tra cứu..."):
        res = trust.ask(uid, st.session_state.q, today=today)
    st.session_state.result = {"uid": uid, "q": st.session_state.q, "r": res}

stored = st.session_state.get("result")
if stored and stored["uid"] == uid:
    r = stored["r"]
    icon, label, color = TYPES.get(r["type"], ("ℹ️", r["type"], "#6b7280"))
    if r.get("notice"):
        st.warning(r["notice"])
    st.markdown(f"<div class='card' style='--c:{color}'><span class='badge' style='--c:{color}'>"
                f"{icon} {label}</span><div class='msg'>{esc(r['message'])}</div></div>", unsafe_allow_html=True)
    if r.get("time_note"):
        st.info(f"🕒 {r['time_note']}")
    for w in r["warnings"]:
        st.warning(w)

    if r["citations"]:
        tab_src, tab_why = st.tabs(["📄 Căn cứ & kiểm chứng", "🧭 Vì sao dùng quy định này"])
        with tab_src:
            for e in r["evidence"]:
                to = f" → {dmy(e['effective_to'])}" if e["effective_to"] else " → nay"
                quote = " ".join(f"<mark>{esc(s['text'])}</mark>" if s["highlight"] else esc(s["text"])
                                 for s in e["quote"])
                st.markdown(
                    f"<div class='src'><b>{esc(e['title'])}</b> <span class='chip'>{esc(e['version'])}</span>"
                    f"<span class='chip'>hiệu lực {dmy(e['effective_from'])}{to}</span>"
                    f"<span class='chip'>{esc(org.get(e['scope'], e['scope']))}</span>"
                    f"<span class='chip'>{esc(e['doc_id'])}</span>"
                    f"<span class='chip'>Người phụ trách: {esc(e['owner'])}</span>"
                    f"<div class='quote'>{quote}</div></div>", unsafe_allow_html=True)
                st.caption("Đoạn trích nguyên văn từ tài liệu; phần tô vàng là câu chứa số liệu có trong câu trả lời.")
                if len(e["history"]) > 1:
                    st.markdown("**Lịch sử phiên bản**")
                    st.table([{"Phiên bản": h["version"], "Hiệu lực từ": dmy(h["effective_from"]),
                               "Đến": dmy(h["effective_to"]), "Trạng thái": h["state"]} for h in e["history"]])
        with tab_why:
            if r["explanations"]:
                for line in r["explanations"]:
                    st.markdown(f"- {line}")
            else:
                st.write("Chỉ có một quy định áp dụng cho chủ đề này.")
    st.caption("Sai, cần cập nhật hoặc chưa rõ? Báo cho người phụ trách tài liệu: "
               + (", ".join(sorted({e["owner"] for e in r["evidence"]})) or "HR / quản trị đơn vị của bạn"))

    if debug:
        st.divider()
        st.subheader("Debug (không hiển thị cho người dùng)")
        d = r.get("debug", {})
        t1, t2 = st.tabs(["Tài liệu bị loại", "Chi tiết xử lý"])
        with t1:
            reasons = {"access": "vượt quyền", "scope": "khác đơn vị", "status": "nháp/thu hồi",
                       "expired": "hết hạn", "not_yet_effective": "chưa hiệu lực"}
            st.table([{"Mã": x["id"], "Tài liệu": x["title"], "Lý do loại": reasons.get(x["reason"], x["reason"])}
                      for x in d.get("rejected", [])])
        with t2:
            st.json({"as_of": r["as_of"], **{k: v for k, v in d.items() if k != "rejected"}})