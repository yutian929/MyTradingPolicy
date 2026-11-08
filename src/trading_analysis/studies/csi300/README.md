# 沪深 300 分析

当前是模块骨架，未实现数据获取、指标计算或图表。

运行入口：`python -m trading_analysis.studies.csi300.run`。

开发顺序：

1. 明确分析问题、日期范围、数据来源及口径。
2. 在 `data.py` 组合与清洗数据，需要时扩展共用 AkShare 数据层。
3. 在 `analysis.py` 实现计算，在 `charts.py` 实现绘图。
4. 在 `run.py` 串联流程，将生成文件保存到项目根目录的 `outputs/`。

多个模块确实需要同一能力时，再将其提取到 `common/`。
