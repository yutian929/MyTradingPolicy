# 探索笔记

用于临时数据探索与图表验证。稳定逻辑移入 `src/trading_analysis/`。
Notebook 的内核应使用安装了本项目的虚拟环境。

## 沪深 300 历年日 K 线

`csi300_daily_kline.ipynb` 通过 AkShare 的新浪指数日线接口获取全部可用历史，
检查 OHLC 数据并绘制可缩放的日 K 线与成交量，导出离线 HTML 到 `outputs/`。

在项目根目录启动：

```bash
source .venv/bin/activate
python -m pip install -e '.[notebook]'
python -m jupyterlab notebooks/csi300_daily_kline.ipynb
```

选择当前虚拟环境的 Python 内核，从上到下运行即可。获取单元格每次都会联网；
实际覆盖日期与交易日数量会打印在输出中。原始行情保存在 `data/raw/`。

## 红利低波公开方法的部分复现

`fuli_time_reproduction.ipynb` 调用 `studies.dividend_low_vol`，对照「复利时光」
公开的午间指标，检查 RSI / MA250、评级版本，以及 RSI 超卖事件的复权敏感性。
默认复用本地真实行情；设 `REFRESH=True` 可重新通过 AkShare 获取。
调查边界和未公开参数见 `research/fuli_time/README.md`，不包含冒充原版的综合评分。

## 真实行情快照与逐项验证

`fuli_time_live.ipynb` 是最新运行入口。默认用2026-11-06的真实缓存完整执行；
2026-11-09午盘后改为 `ASOF='2026-11-09 11:30:00'`、`CACHE_ONLY=False`。
它输出52项原图字段和3项新增MACD字段及各自实现状态，缺失项保留原因，综合评分明确标为代理模型。
详细运行和核验步骤见 `src/trading_analysis/studies/dividend_low_vol/RUNBOOK.md`。
