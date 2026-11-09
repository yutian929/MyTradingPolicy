"""Similarity controls and persisted search results for the main chart."""
import pandas as pd
import streamlit as st

from trading_analysis.dashboard.similarity import find_similar_periods, period_label


def render_similarity(frame, context):
    fingerprint = int(pd.util.hash_pandas_object(frame[["date", "close"]], index=False).sum())
    context = (context, fingerprint)
    if st.session_state.get("similarity_context") != context:
        st.session_state["similarity_context"] = context
        st.session_state.pop("similarity_result", None)
        st.session_state.pop("similarity_focus", None)
    with st.container():
        with st.form("similarity_search", border=False):
            left, right, action, reset = st.columns([2, 2, 1, 1], vertical_alignment="bottom")
            m = int(left.number_input("M · 样本交易日数", min_value=3, value=30, step=1))
            n = int(right.number_input("N · 最多返回区间数", min_value=1, max_value=20, value=5, step=1))
            with action:
                search = st.form_submit_button("相关", width="stretch")
            with reset:
                overview = st.form_submit_button("返回全景", width="stretch")
        if overview:
            st.session_state.pop("similarity_focus", None)
        if search or overview:
            st.session_state["similarity_revision"] = st.session_state.get("similarity_revision", 0) + 1
        if search:
            st.session_state.pop("similarity_result", None)
            st.session_state.pop("similarity_focus", None)
            try:
                matches = find_similar_periods(frame, m, n)
            except ValueError as exc:
                st.warning(str(exc))
            else:
                st.session_state["similarity_result"] = dict(m=m, n=n, matches=matches)
        result = st.session_state.get("similarity_result")
        if result is None:
            return {}
        matches = result["matches"]
        sample = (frame.date.iloc[-result["m"]], frame.date.iloc[-1])
        if len(matches) < result["n"]:
            st.info(f"找到 {len(matches)} / {result['n']} 段：仅展示有效、正相关且互不重叠的历史区间。")
        for rank, item in enumerate(matches, 1):
            if st.button(f"{period_label(rank)}  {item.score:.1%} · {item.start:%Y-%m-%d} ～ "
                         f"{item.end:%Y-%m-%d} · 定位", key=f"similarity_locate_{rank}",
                         help=f"Pearson r = {item.score:.4f}", width="stretch"):
                st.session_state["similarity_focus"] = rank
        return dict(similarities=matches, sample_range=sample,
                    focus_rank=st.session_state.get("similarity_focus"),
                    view_revision=f"{fingerprint}-{st.session_state.get('similarity_revision', 0)}-"
                                  f"{st.session_state.get('similarity_focus')}")
