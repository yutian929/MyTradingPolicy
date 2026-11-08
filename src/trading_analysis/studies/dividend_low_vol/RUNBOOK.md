# 红利低波：真实行情复现与周一验证

当前版本已经能从 AkShare 的真实日线、分钟线、国债和中证指数数据生成可追溯快照。**完整原策略尚未还原**：技术指标近期验证通过，评分为近似模型，原回测样本和部分估值数据仍未匹配。

## 周一运行

在项目根目录、2026年11月9日11:30之后运行（分钟数据刚结束时可能稍有发布延迟）：

```bash
.venv/bin/python -m trading_analysis.studies.dividend_low_vol snapshot \
  --asof '2026-11-09 11:30:00'
```

输出位于 `outputs/fuli_time_reproduction/20261109_113000/`：

- `report.html`：离线交互价格、均线、布林、RSI、KDJ、MACD及条件收益图；全部对应字段和状态。
- `snapshot.json`：指标、算法版本、参数、数据源、实际抓取时间、市场截止时间、缺失原因。
- `metrics.csv`：逐项结果；百分数按展示单位保存，例如4.70表示4.70%。
- `indicator_history.csv`：截止时刻之前的完整指标序列。
- `conditional_samples.csv` / `conditional_histogram.csv`：独立代理模型的60日条件收益样本和分箱。
- `observations_template.csv`：填入博主当天数值，供独立核验。

先保存预测，再录入博主数据；不要拿当天博主数值替换计算输入。把模板的 `observed_value` 填好，另存 `observations_filled.csv`，然后运行：

```bash
.venv/bin/python -m trading_analysis.studies.dividend_low_vol compare \
  --snapshot outputs/fuli_time_reproduction/20261109_113000/snapshot.json \
  --observed outputs/fuli_time_reproduction/20261109_113000/observations_filled.csv \
  --output outputs/fuli_time_reproduction/20261109_113000/comparison.csv
```

截止时刻未到、当天不是交易日、分钟缺失或接口失败时，程序会明确报错。不会把旧日行情或当天收盘高低价、成交量当成午盘输入。估值接口失败不妨碍输出技术指标，相关字段保留空白及原因。

## 已执行的演示

`notebooks/fuli_time_live.ipynb` 已完整执行，默认2026-11-06 11:30、`CACHE_ONLY=True`。明天把 `ASOF` 改为11月9日，`CACHE_ONLY=False`。

同一份真实数据的离线命令：

```bash
.venv/bin/python -m trading_analysis.studies.dividend_low_vol snapshot \
  --asof '2026-11-06 11:30:00' --cache-only
```

仅在复盘收盘口径时使用 `15:00:00`。不能将它与博主11:30记录直接混作同一验证。

## 校准与误差

选择算法参数只用9–10月；11月2–6日为留出样本。真实分钟数据可独立重建27个发帖日，另有39日收盘对照及作者价格输入的公式诊断；后两者不能冒充独立午盘验证。

| 功能 | 当前结果 |
|---|---|
| 价格、涨跌、RSI、MA250乖离、KDJ、动量、波动、量比、布林位置、52周位置、连涨跌 | 15项，近期留出75/75达到容差；训练期233/327达到容差，异常保留 |
| DY、10Y国债、股债差 | 近期5日分别最大误差0、0.0043、0.0043个百分点；10月DY存在最高0.51个百分点差异 |
| 综合评分代理 | 真实午盘留出平均误差约1.403分，最大3.635分；3分目标有一天未通过 |
| 综合评级代理 | 留出5日评级一致；边界附近仍提示不确定，A级边界没有已观察样本支持 |
| 操作提示 | 推断分段；误差区间跨操作边界或输入超训练域时不输出确定动作 |
| 原作者同分60日回测 | 尚未复现。已实现独立前复权、成熟标签条件收益统计，与原样本数及均值存在显著差异 |
| PE/PB、ROE、十年估值分位、十年利差历史统计、拥挤度 | 同源输入或公式缺失，输出null及原因；CSI其他PE仅作为不同口径诊断 |
| 周线KDJ/RSI/布林、MA5 | 已计算；周J仅有一个作者价格辅助样本吻合，验证不足 |

逐字段对应表为 `outputs/fuli_time_reproduction/function_matrix.csv`（52个原图字段，加3个新增MACD字段）。原始误差明细见同目录 `technical_validation.csv`、`valuation_validation.csv`、`score_validation.csv`。MACD属于新增分析功能，没有博主对应值，不计入原来的75项验证。

## 新增MACD

MACD(12,26,9)使用与其他日线指标相同的512890不复权价格；午盘时最后一根日K为截止11:30的部分K线。DIF为EMA12减EMA26，DEA为DIF的EMA9，柱值为 **2×(DIF−DEA)**。EMA采用递推式（`adjust=False`），以首个收盘价初始化，DEA从0初始化；前33条观测留空，第34条起展示。不同软件的初始化或柱值倍数可能不同。

报告新增独立MACD面板，正柱红色、负柱绿色。快照、CSV和完整历史序列导出 `macd_dif`、`macd_dea`、`macd_histogram`，单位与价格一致（元）。快照来源中记录参数及初始化方式。MACD不参与当前冻结的代理评分，也没有虚构博主验证误差或验收阈值。

容差见 `pipeline.TOLERANCES`：价格0.001；RSI/K/D/J各0.1；乖离与动量0.01个百分点；量比0.01；波动0.06个百分点；布林和52周位置0.55个百分点。评分3分为研究目标，不表示已全部达标。代理模型中的±5分带只是保守边界提示，不是统计置信区间。

## 与图中文字不同的推断

- 52周位置用滚动收盘价高低点；240/250/252/260交易日及365日历候选在当前样本极值相同，无法唯一识别窗口，显式固定252交易日。
- 量比更匹配5日均量/20日均量，包含当天午间累计量。图中文字写当日量/20日均量，两者并列保留。
- 波动率更匹配20日简单收益样本标准差×√250；图中文字写√252。默认公开指标函数保留原口径，生产复现显式使用 `calibrated_config()`。
- 已观察评级更符合20分一档，图例却写25/40/55/70。原图阈值与代理评级同时保留。

10月28日实际11:30价格1.218，原帖1.212，导致多项指标不符。不能用改价格、删除失败日期的方式宣称全期通过。

## 来源与时间

行情：ETF512890；估值：指数H30269。这两个层次不混称同一个指数价格。估值和国债严格选择截止日期之前的可用记录。CSI DY是近期验证的候选来源；它并不证明CSI全部估值口径等同蛋卷/雪球。

AkShare支持的ETF一分钟数据限近5个交易日；更长分钟粒度也有服务端历史范围限制，及时保存快照便于复盘。接口与字段参考 [AkShare ETF文档](https://akshare.akfamily.xyz/data/fund/fund_public.html#etf)；实际请求参数、版本和SHA256保存在本地缓存元数据。

综合评分系数冻结于10月30日，输入为重新计算的RSI、年线乖离、KDJ-J、布林位置；预测函数不读取作者档案、当前评分或日期查表。历史收益统计使用前复权价格，标签结束日严格早于截止日；这是把固定代理模型用于历史的条件统计，不是当年可执行的逐日训练回测。

## 测试

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m trading_analysis.studies.dividend_low_vol.technical_validation
```

单元测试覆盖指标递推、周线和分钟未来数据隔离、缓存完整性、估值发布日期、缺失处理、评分域外与边界处理、成熟收益标签。可选交互图依赖项目已有 `notebook` extra。
