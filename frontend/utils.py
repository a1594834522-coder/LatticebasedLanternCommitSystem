"""前端公共工具。"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

import streamlit as st


def parse_vector(text: str) -> List[int]:
    items = [item.strip() for item in text.replace("\n", ",").split(",") if item.strip()]
    if not items:
        raise ValueError("请输入至少一个整数")
    vector: List[int] = []
    for item in items:
        try:
            vector.append(int(item))
        except ValueError as exc:
            raise ValueError(f"无法解析为整数: {item}") from exc
    return vector


def display_status_badge(status: str) -> None:
    status_map = {
        "created": "gray",
        "rules_submitted": "blue",
        "vector_submitted": "blue",
        "awaiting_consent": "orange",
        "ready": "orange",
        "in_progress": "orange",
        "completed": "green",
        "failed": "red",
        "rejected": "red",
    }
    color = status_map.get(status, "gray")
    st.markdown(f"<span style='padding:4px 8px;border-radius:4px;background:{color};color:white;'>{status}</span>", unsafe_allow_html=True)


def pretty_json(data: Dict[str, Any]) -> None:
    st.code(json.dumps(data, ensure_ascii=False, indent=2), language="json")


def vector_summary(vector: Iterable[int]) -> str:
    vec = list(vector)
    if len(vec) <= 6:
        return str(vec)
    return f"[{', '.join(map(str, vec[:3]))}, ... , {', '.join(map(str, vec[-3:]))}] (共 {len(vec)} 项)"
