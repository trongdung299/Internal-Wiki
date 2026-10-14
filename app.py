"""Giao diện demo tối giản: streamlit run app.py"""
from datetime import date

import streamlit as st

import retrieve as core
import llm
import pipeline

st.set_page_config(page_title="Tri thức nội bộ Appota", page_icon="📘")
st.title("📘 Tra cứu quy định nội bộ")

users = core.load_users()
uid = st.sidebar.selectbox("Đăng nhập (giả lập)", list(users),
                           format_func=lambda i: f"{users[i]['name']} · {users[i]['role']}")
u = users[uid]
st.sidebar.caption(f"Đơn vị: {core.load_org().get(u['unit'], u['unit'])}")
today = st.sidebar.date_input("Ngày tra cứu", date.today())
debug = st.sidebar.checkbox("Debug (chỉ nội bộ)")

q = st.text_input("Câu hỏi", placeholder="Quy định nghỉ phép của tôi như thế nào?")
if st.button("Hỏi") and q.strip():
    with st.spinner("Đang tra cứu..."):
        r = pipeline.run(uid, q, today=today)
    {"answer": st.success, "conflict": st.warning, "clarify": st.info}.get(r["type"], st.error)(r["message"])
    for w in r["warnings"]:
        st.warning(w)
    if r["citations"]:
        st.markdown("**Căn cứ**")
        for c in r["citations"]:
            st.write(f"- {c['title']} · {c['version']} · hiệu lực từ {llm.fmt_date(c['effective_from'])} "
                     f"· {c['scope_name']} (`{c['doc_id']}`)")
    st.caption("Sai / cần cập nhật / chưa rõ? Báo cho chủ tài liệu: "
               + ", ".join(sorted({c["owner"] for c in r["citations"]})) if r["citations"] else "")
    if debug:
        st.json(r["debug"])