"""Lantern 证明者控制台 (Streamlit)。"""

from __future__ import annotations

import io
import json
from typing import List

import streamlit as st

from frontend.api import get_client
from frontend.config import load_config
from frontend.state import get_state
from frontend.utils import display_status_badge, parse_vector, pretty_json

cfg = load_config()
st.set_page_config(page_title=f"{cfg.app_title} · 证明者", layout="wide")
st.title("🔐 Lantern 证明者控制台")

state = get_state()
client = get_client()


def refresh_sessions() -> None:
    try:
        state["sessions"] = client.list_sessions()
    except RuntimeError as err:
        st.error(f"会话列表获取失败: {err}")


state.setdefault("sessions", [])
state.setdefault("vector_text", "")

with st.sidebar:
    st.markdown("### 当前会话列表")
    if st.button("刷新列表", use_container_width=True):
        refresh_sessions()
    if not state["sessions"]:
        refresh_sessions()
    sessions = state.get("sessions", [])
    if sessions:
        selected = st.selectbox(
            "选择会话",
            options=sessions,
            format_func=lambda item: f"{item['session_id']} · {item['status']}",
        )
        if selected:
            state["session_id"] = selected["session_id"]
    else:
        st.caption("暂无可加入的会话，请联系验证者创建。")

session_id = st.text_input("会话 ID", value=state.get("session_id", "")).strip()
col_load, col_refresh = st.columns([1, 1])
with col_load:
    if st.button("加载会话", use_container_width=True):
        if not session_id:
            st.warning("请先输入或选择会话 ID")
        else:
            try:
                session = client.get_session(session_id)
                state["session_id"] = session_id
                state["session"] = session
                st.success("会话信息已加载")
            except RuntimeError as err:
                st.error(str(err))
with col_refresh:
    if st.button("立即刷新", use_container_width=True):
        if state.get("session_id"):
            try:
                state["session"] = client.get_session(state["session_id"])
            except RuntimeError as err:
                st.error(str(err))

if state.get("session_id"):
    st.experimental_set_query_params(session_id=state["session_id"])
    st.sidebar.markdown(f"**当前会话:** `{state['session_id']}`")

if not state.get("session"):
    st.info("加载会话后即可查看详情。")
    st.stop()

session = state["session"]

st.subheader("当前状态")
left, right = st.columns([1, 3])
with left:
    display_status_badge(session.get("status", "unknown"))
with right:
    meta = session.get("metadata", {})
    if meta:
        st.markdown("**会话元数据**")
        pretty_json(meta)
    st.markdown("**历史事件**")
    history_rows = session.get("history", [])
    if history_rows:
        for event in history_rows[-5:]:
            st.write(f"- {event['timestamp']} · {event['event_type']}")
    else:
        st.caption("暂无事件")

st.divider()

st.header("提交向量（仅保存在本地）")
vector_area, upload_area = st.columns([2, 1])
with vector_area:
    vector_text = st.text_area(
        "输入向量（逗号或换行分隔）",
        value=state.get("vector_text", ""),
        height=160,
    )
    state["vector_text"] = vector_text
with upload_area:
    uploaded = st.file_uploader("或上传 CSV/文本文件", type=["txt", "csv"])
    if uploaded:
        try:
            content = uploaded.read().decode("utf-8")
            state["vector_text"] = content
            st.success("已读取文件内容，文本框已更新")
        except Exception as err:
            st.error(f"文件读取失败: {err}")

if st.button("提交向量到后端", type="primary"):
    if not state.get("session_id"):
        st.warning("请先加载会话")
    else:
        try:
            vector = parse_vector(state.get("vector_text", ""))
            session = client.submit_vector(state["session_id"], vector)
            state["session"] = session
            st.success(f"已提交向量（长度 {len(vector)}），等待验证者确认并同意执行。")
        except ValueError as err:
            st.error(str(err))
        except RuntimeError as err:
            st.error(str(err))

st.divider()

st.header("规则与状态概览")
col_rules, col_meta = st.columns([2, 1])
with col_rules:
    st.markdown("**验证者提供的规则**")
    rules_payload = session.get("rules") or {}
    if rules_payload:
        pretty_json(rules_payload)
    else:
        st.caption("尚未收到规则，请等待验证者提交。")
with col_meta:
    st.markdown("**最新验证结果**")
    proof_meta = session.get("proof_metadata")
    if proof_meta:
        pretty_json(proof_meta)
    else:
        st.caption("证明尚未生成。")

st.divider()

st.header("同意 / 拒绝执行")
reject_reason = st.text_input("拒绝原因 (可选)", key="reject_reason")
columns = st.columns(3)
with columns[0]:
    if st.button("同意执行", type="primary", use_container_width=True):
        try:
            session = client.submit_consent(state["session_id"], "agreed")
            state["session"] = session
            st.success("已同意执行，后端正在生成证明。")
        except RuntimeError as err:
            st.error(str(err))
with columns[1]:
    if st.button("拒绝执行", use_container_width=True):
        try:
            session = client.submit_consent(state["session_id"], "rejected", reject_reason or None)
            state["session"] = session
            st.warning("已拒绝执行。")
        except RuntimeError as err:
            st.error(str(err))
with columns[2]:
    if st.button("重新加载会话", use_container_width=True):
        try:
            state["session"] = client.get_session(state["session_id"])
        except RuntimeError as err:
            st.error(str(err))

st.divider()

if session.get("status") in {"completed", "failed"} and session.get("proof_available"):
    st.header("下载证明包")
    try:
        proof = client.download_proof(state["session_id"])
        buffer = io.BytesIO(json.dumps(proof, ensure_ascii=False, indent=2).encode("utf-8"))
        st.download_button(
            "下载 proof.json",
            buffer,
            file_name=f"proof_{state['session_id']}.json",
            mime="application/json",
        )
        st.success("证明包已准备好。")
    except RuntimeError as err:
        st.error(str(err))
else:
    st.info("证明尚未生成或正在处理中。")
