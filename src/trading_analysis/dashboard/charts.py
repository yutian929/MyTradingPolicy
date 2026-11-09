"""Plotly daily candles and independently selectable moving averages."""
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from trading_analysis.dashboard.data import PERIODS
from trading_analysis.dashboard.valuation import PREMIUM

# Ascending periods use distinct hues with decreasing lightness; avoid candle reds/greens.
COLORS = ("#c9b45a", "#63a9ce", "#a684c5", "#4b6c9e", "#684074", "#30343b")
PANELS = ("成交量", "MACD", "RSI")


def available_panels(frame, *, nav=False):
    return [name for name in PANELS if name != "成交量" or (not nav and "volume" in frame)]


def build_chart(frame, selected=PERIODS, *, nav=False, panels=("成交量",), valuations=()):
    panels = [name for name in available_panels(frame, nav=nav) if name in panels]
    panel_count = len(panels) + len(valuations)
    fig = make_subplots(rows=1 + panel_count, cols=1, shared_xaxes=True,
                        vertical_spacing=0.035, row_heights=[3] + [1] * panel_count)
    if nav:
        fig.add_trace(go.Scatter(x=frame.date, y=frame.close, name="单位净值",
                                line=dict(color="#0284c7", width=2), showlegend=False), row=1, col=1)
    else:
        fig.add_trace(go.Candlestick(x=frame.date, open=frame.open, high=frame.high,
                                    low=frame.low, close=frame.close, name="日 K", showlegend=False,
                                    increasing=dict(line=dict(color="#ef4444"), fillcolor="#ef4444"),
                                    decreasing=dict(line=dict(color="#10b981"), fillcolor="#10b981")), row=1, col=1)
    for period, color in zip(PERIODS, COLORS):
        if period in selected:
            fig.add_trace(go.Scatter(x=frame.date, y=frame[f"MA{period}"], name=f"MA{period}",
                                    line=dict(color=color, width=1.5), connectgaps=False), row=1, col=1)
    for row, panel in enumerate(panels, start=2):
        if panel == "成交量":
            colors = ["#ef4444" if c >= o else "#10b981"
                      for c, o in zip(frame.close, frame.open)]
            # White template borders erase subpixel bars when years of days fit on screen.
            # A matching one-pixel stroke keeps dense bars visible without aggregating data.
            fig.add_trace(go.Bar(x=frame.date, y=frame.volume, name="成交量（手）",
                                marker=dict(color=colors, line=dict(color=colors, width=1)),
                                showlegend=False), row=row, col=1)
            fig.update_yaxes(title_text="成交量（手）", row=row, col=1)
        elif panel == "MACD":
            colors = ["#ef4444" if value >= 0 else "#10b981" for value in frame.macd_histogram]
            fig.add_trace(go.Bar(x=frame.date, y=frame.macd_histogram, name="MACD 柱", showlegend=False,
                                marker=dict(color=colors, line=dict(color=colors, width=1))), row=row, col=1)
            for column, name, color in (("macd_dif", "DIF", "#c9a43b"),
                                        ("macd_dea", "DEA", "#684074")):
                fig.add_trace(go.Scatter(x=frame.date, y=frame[column], name=name,
                                        line=dict(color=color, width=1.5), connectgaps=False,
                                        showlegend=False), row=row, col=1)
            fig.update_yaxes(title_text="MACD (12,26,9)", zeroline=True,
                             zerolinecolor="#a3a3a3", row=row, col=1)
        elif panel == "RSI":
            fig.add_trace(go.Scatter(x=frame.date, y=frame.rsi14, name="RSI (14)",
                                    line=dict(color="#4b6c9e", width=1.5), connectgaps=False,
                                    showlegend=False), row=row, col=1)
            for level in (30, 70):
                fig.add_hline(y=level, line_color="#a3a3a3", line_dash="dash", line_width=1,
                              row=row, col=1)
            fig.update_yaxes(title_text="RSI (14)", range=[0, 100],
                             tickvals=[0, 30, 50, 70, 100], row=row, col=1)
    for row, item in enumerate(valuations, start=2 + len(panels)):
        history = item.frame.loc[item.frame.date.between(frame.date.min(), frame.date.max())]
        # Preserve source dates and missing trading days; never carry an old valuation forward.
        dates = frame.set_index("date").index.union(history.set_index("date").index).sort_values()
        values = history.set_index("date").value.reindex(dates)
        fig.add_trace(go.Scatter(x=dates, y=values, mode="lines", name=item.metric,
                                line=dict(color="#684074", width=1.8), connectgaps=False,
                                showlegend=False,
                                hovertemplate=item.metric + ": %{y:.3f}" + item.unit
                                + "<br>数据日期：%{x|%Y-%m-%d}<extra></extra>"), row=row, col=1)
        fig.update_yaxes(title_text=f"{item.metric}（{item.unit}）", row=row, col=1)
        if item.metric == PREMIUM:
            fig.add_hline(y=0, line_color="#a3a3a3", line_dash="dot", row=row, col=1)
    fig.update_layout(height=500 + 180 * panel_count, template="plotly_white", margin=dict(l=10, r=10, t=25, b=10),
                      paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", hovermode="x unified",
                      hoversubplots="axis", hoverdistance=20, spikedistance=-1,
                      font=dict(color="#404040"),
                      hoverlabel=dict(bgcolor="#ffffff", bordercolor="#d4d4d4", font_color="#262626"),
                      legend=dict(orientation="h", y=1.08), dragmode="pan")
    fig.update_xaxes(rangeslider_visible=False, showgrid=False,
                     range=[frame.date.min(), frame.date.max()])
    fig.update_yaxes(gridcolor="#eeeeee", zerolinecolor="#d4d4d4", fixedrange=False)
    # Matched axes synchronize zoom only. Hover propagation needs one actual x axis
    # shared by every trace, anchored at the bottom while keeping each y domain.
    fig.update_traces(xaxis="x")
    fig.update_yaxes(anchor="x")
    for shape in fig.layout.shapes:
        if shape.xref and shape.xref.startswith("x"):
            shape.xref = "x domain" if shape.xref.endswith(" domain") else "x"
    for row in range(2, panel_count + 2):
        fig.layout[f"xaxis{row}"] = None
    fig.update_layout(xaxis=dict(matches=None, anchor=f"y{panel_count + 1}" if panel_count else "y",
                                 showticklabels=True, showspikes=True, spikemode="across",
                                 spikesnap="data", spikecolor="#737373", spikethickness=1,
                                 spikedash="dash", hoverformat="%Y-%m-%d"))
    return fig
