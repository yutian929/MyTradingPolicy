"""Plotly daily candles and independently selectable moving averages."""
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from trading_analysis.dashboard.data import PERIODS

# Ascending periods use distinct hues with decreasing lightness; avoid candle reds/greens.
COLORS = ("#c9b45a", "#63a9ce", "#a684c5", "#4b6c9e", "#684074", "#30343b")


def build_chart(frame, selected=PERIODS, *, nav=False):
    volume = not nav and "volume" in frame
    fig = make_subplots(rows=2 if volume else 1, cols=1, shared_xaxes=True,
                        vertical_spacing=0.035, row_heights=[0.8, 0.2] if volume else [1])
    if nav:
        fig.add_trace(go.Scatter(x=frame.date, y=frame.close, name="单位净值",
                                line=dict(color="#0284c7", width=2)), row=1, col=1)
    else:
        fig.add_trace(go.Candlestick(x=frame.date, open=frame.open, high=frame.high,
                                    low=frame.low, close=frame.close, name="日 K",
                                    increasing=dict(line=dict(color="#ef4444"), fillcolor="#ef4444"),
                                    decreasing=dict(line=dict(color="#10b981"), fillcolor="#10b981")), row=1, col=1)
    for period, color in zip(PERIODS, COLORS):
        if period in selected:
            fig.add_trace(go.Scatter(x=frame.date, y=frame[f"MA{period}"], name=f"MA{period}",
                                    line=dict(color=color, width=1.5), connectgaps=False), row=1, col=1)
    if volume:
        fig.add_trace(go.Bar(x=frame.date, y=frame.volume, name="成交量（手）",
                            marker_color=["#ef4444" if c >= o else "#10b981"
                                          for c, o in zip(frame.close, frame.open)], showlegend=False), row=2, col=1)
    fig.update_layout(height=680, template="plotly_white", margin=dict(l=10, r=10, t=25, b=10),
                      paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", hovermode="x unified",
                      font=dict(color="#404040"),
                      hoverlabel=dict(bgcolor="#ffffff", bordercolor="#d4d4d4", font_color="#262626"),
                      legend=dict(orientation="h", y=1.08), dragmode="pan")
    fig.update_xaxes(rangeslider_visible=False, showgrid=False,
                     range=[frame.date.min(), frame.date.max()])
    fig.update_yaxes(gridcolor="#eeeeee", zerolinecolor="#d4d4d4", fixedrange=False)
    return fig
