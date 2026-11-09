"""Load optional valuation subplots and render their supporting details."""
import numpy as np
import streamlit as st

from trading_analysis.dashboard.valuation import (
    PREMIUM, historical_percentile, load_valuation, read_source, valuation_position,
)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_valuation_source(api, params):
    return read_source(api, params)


def load_selected_valuations(symbol, kind, metrics):
    items = []
    for metric in metrics:
        try:
            with st.spinner(f"正在加载{metric}…"):
                items.append(load_valuation(symbol, kind, metric, reader=fetch_valuation_source))
        except Exception as exc:
            st.warning(f"{metric} 暂不可用，行情和其他指标仍可使用。")
            with st.expander("查看数据问题"):
                st.write(str(exc))
    return items


def render_valuation_details(symbol, kind, items, start, end):
    if not items:
        return
    with st.expander("副图指标说明与数据"):
        _render_details(symbol, kind, items, start, end)


def _render_details(symbol, kind, items, start, end):
    metrics = [item.metric for item in items]
    show_rank = False
    years = 5
    if metrics != [PREMIUM]:
        show_rank = st.checkbox("显示历史分位", value=True)
        if show_rank:
            years = st.selectbox("分位比较窗口", [1, 3, 5, 10], index=2,
                                 format_func=lambda value: f"近{value}年")
            st.caption("分位按所选窗口内有效观测计算，包含最近记录；PE/PB 分位低表示相对历史便宜，股息率方向相反。"
                       "20% / 80% 仅作区间标记，不代表未来涨跌概率。")
    for item in items:
        metric = item.metric
        with st.container(border=True):
            st.write(f"**{metric}**")
            latest = item.frame.iloc[-1]
            finite = np.isfinite(latest.value)
            columns = st.columns(2) if show_rank else st.columns(1)
            columns[0].metric("最近可用记录", f"{latest.value:,.2f} {item.unit}" if finite else "—")
            if not finite:
                st.caption("最近记录缺失或不适用，未替换为更早数值；详见计算口径。")
            if show_rank:
                rank = historical_percentile(item.frame, years)
                columns[1].metric(f"近{years}年历史分位", f"{rank['value']:.1f}%" if rank['value'] is not None else "—")
                if rank["value"] is not None:
                    position = "历史样本无变化，不作高低判断" if rank["constant"] else valuation_position(metric, rank["value"])
                    st.caption(f"{position} · "
                               f"比较样本：{rank['start']:%Y-%m-%d} — {rank['end']:%Y-%m-%d}，{rank['count']} 条有效观测。")
                else:
                    st.caption(f"{rank['reason']} 当前窗口有 {rank['count']} 条有效观测。")
            elif finite and metric == PREMIUM:
                st.caption("溢价：场内收盘价高于同日净值。" if latest.value > 0 else
                           "折价：场内收盘价低于同日净值。" if latest.value < 0 else "场内收盘价与同日净值相等。")
            st.caption(f"数据日期：{latest.date:%Y-%m-%d} · "
                       f"历史覆盖：{item.frame.date.min():%Y-%m-%d} — {item.frame.date.max():%Y-%m-%d}，"
                       f"{len(item.frame)} 条记录。曲线使用上方所选行情时间范围。")
            if item.metric == PREMIUM:
                st.caption("日终折溢价，不是盘中 IOPV；黄金 ETF 折溢价不等于黄金本身的估值。")
            if not item.frame.date.between(start, end).any():
                st.info("所选行情时间范围内没有该指标的数据。")
            with st.expander("计算口径与数据"):
                st.write(item.formula)
                st.write(item.note)
                if show_rank:
                    st.write("历史分位 = 窗口内小于或等于最近值的有效观测数 ÷ 有效观测总数 × 100%。"
                             "至少30个有效样本且覆盖所选年限（允许首日31天误差），有效记录间不能有超过120天的缺口，缺失值不填充。")
                for source in item.sources:
                    st.caption(f"{source.get('provider', '数据源')} · {source.get('api', '')} · "
                               f"获取时间：{source.get('fetched_at', '未知')}")
                st.dataframe(item.frame, hide_index=True, width="stretch")
                st.download_button("下载估值数据 CSV", item.frame.to_csv(index=False).encode("utf-8-sig"),
                                   file_name=f"{symbol}_{metric}.csv", mime="text/csv",
                                   key=f"valuation_csv_{kind}_{symbol}_{metric}")
