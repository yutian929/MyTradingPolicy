"""Run with streamlit run src/trading_analysis/dashboard/app.py."""
import os
import streamlit as st

from trading_analysis.cli import TYPE_LABELS

from trading_analysis.dashboard.charts import available_panels, build_chart
from trading_analysis.dashboard.data import KINDS, PERIODS, load_history, select_range
from trading_analysis.dashboard.valuation import valuation_options
from trading_analysis.dashboard.similarity_view import render_similarity
from trading_analysis.dashboard.valuation_view import (
    fetch_valuation_source, load_selected_valuations, render_valuation_details,
)

st.set_page_config(page_title="行情看板", layout="wide")
# Keep interface accents neutral without changing financial chart colors.
st.html("""<style>
html { color-scheme: light; }
[data-testid="stAlert"] { background: #f5f5f5; color: #404040; }
h1, h2, h3 { font-weight: 500 !important; }
[data-testid="stMetricValue"] { font-weight: 400; }
</style>""")
initial_symbol = os.environ.get("MTP_VIEWER_SYMBOL", "000300")
initial_kind = TYPE_LABELS.get(os.environ.get("MTP_VIEWER_TYPE", "index"), "指数")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch(symbol, kind, adjust):
    return load_history(symbol, kind, adjust)


st.title("行情看板")
with st.sidebar:
    st.header("选择标的")
    kind = st.selectbox("标的类型", list(KINDS), index=list(KINDS).index(initial_kind))
    with st.form("query"):
        symbol = st.text_input("股票 / 指数 / 基金代码", value=initial_symbol, max_chars=6)
        adjustable = kind not in ("指数", "基金（场外）")
        adjustment = st.selectbox("价格口径", ["不复权", "前复权", "后复权"] if adjustable else ["不复权"])
        submitted = st.form_submit_button("查询行情", width="stretch", type="primary")
    st.caption("示例：股票 600519 · 指数 000300 · ETF 510300 · LOF 161725 · 场外基金 050025。代码可能重名，请选择对应类型。")
    refresh = st.button("刷新当前行情", width="stretch")

if submitted:
    st.session_state["request"] = (symbol.strip(), kind, {"不复权": "", "前复权": "qfq", "后复权": "hfq"}[adjustment])
request = st.session_state.get("request", (initial_symbol, initial_kind, ""))
if refresh:
    fetch.clear(*request)
    fetch_valuation_source.clear()
try:
    with st.spinner("正在获取全部历史日线，最多等待 60 秒…"):
        bundle = fetch(*request)
except Exception as exc:
    st.error(f"行情加载失败：{exc}")
    st.info("请检查代码与标的类型，或稍后点击刷新重试。")
    st.stop()

full = bundle.frame
nav = bundle.metadata["nav"]
st.subheader(f"{request[0]} · {request[1]}")
a, b, c = st.columns(3)
a.metric("最新单位净值" if nav else "最新收盘", f"{full.close.iloc[-1]:,.4f}")
b.metric("最新数据日期", full.date.max().strftime("%Y-%m-%d"))
c.metric("历史记录", f"{len(full):,} 条")
range_label = st.radio("显示范围", ["全部", "10年", "5年", "1年"], horizontal=True)
selected = st.multiselect("主图指标", PERIODS, default=list(PERIODS),
                         format_func=lambda n: f"MA{n}",
                         help="可移除均线，也可点击图例临时隐藏。")
panel_options = available_panels(full, nav=nav)
valuation_choices = valuation_options(request[0], request[1])
selected_panels = st.multiselect("副图指标", panel_options + valuation_choices,
                                default=["成交量"] if "成交量" in panel_options else [],
                                key=f"panel_selection_{request[1]}_{request[0]}",
                                help="统一选择成交量、MACD、RSI（14）和当前标的适用的估值指标，也可全部清空。估值数据按需加载。")
panels = [name for name in selected_panels if name in panel_options]
valuation_metrics = [name for name in selected_panels if name in valuation_choices]
years = {"全部": None, "10年": 10, "5年": 5, "1年": 1}[range_label]
visible = select_range(full, years)
st.caption(f"{visible.date.min():%Y-%m-%d} — {visible.date.max():%Y-%m-%d} · {len(visible):,} 条日线 · "
           f"价格口径：{dict(zip(('', 'qfq', 'hfq'), ('不复权', '前复权', '后复权')))[request[2]]}")
if years and len(visible) == len(full):
    st.info(f"可用历史不足或恰好 {years} 年，已展示全部可用历史。")
if nav:
    st.info("场外基金没有开高低收日 K，展示单位净值曲线；均线按净值记录计算，未做分红再投资调整。")
valuations = load_selected_valuations(request[0], request[1], valuation_metrics)
for item in valuations:
    if not item.frame.loc[item.frame.date.between(visible.date.min(), visible.date.max()), "value"].notna().any():
        st.info(f"{item.metric}：所选行情时间范围内没有有效数据。")
chart_area = st.container()
similarity_options = render_similarity(visible, (request, range_label))
chart_area.plotly_chart(build_chart(visible, selected, nav=nav, panels=panels, valuations=valuations,
                           **similarity_options), width="stretch", theme=None,
                config={"scrollZoom": True, "displaylogo": False})
if "MACD" in panels and full.macd_dif.notna().sum() == 0:
    st.info("可用历史不足 34 条，MACD 暂无有效值。")
if "RSI" in panels and full.rsi14.notna().sum() == 0:
    st.info("RSI 暂无有效值：需至少 15 条价格记录，且历史中存在涨跌。")
with st.expander("查看日线数据 / 下载"):
    st.dataframe(visible, width="stretch", hide_index=True)
    st.download_button("下载当前范围 CSV", visible.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{request[0]}_{range_label}.csv", mime="text/csv")
render_valuation_details(request[0], request[1], valuations, visible.date.min(), visible.date.max())
