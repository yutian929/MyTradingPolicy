# MyTradingPolicy

使用 AkShare 做个人市场分析与可视化。按分析主题组织独立模块，复用数据层和通用计算能力。

已提供 `notebooks/csi300_daily_kline.ipynb`，
用于获取沪深 300 全部可用历史日线并绘制交互式 K 线和成交量。
Notebook 安装与启动方法见 `notebooks/README.md`。

另提供 `notebooks/fuli_time_reproduction.ipynb` 和 `studies/dividend_low_vol/`，
用于复现「复利时光」公开的红利低波基础指标并核验历史样本。
完整调查记录见 `research/fuli_time/README.md`；综合评分的未公开部分尚未还原。

最新真实行情入口为 `notebooks/fuli_time_live.ipynb`，支持午盘指标快照、离线报告和
逐项误差对比。技术指标已做独立留出验证；综合评分为代理模型，部分估值与原回测
尚未还原。运行命令、52项对应情况和误差边界见
[红利低波运行说明](src/trading_analysis/studies/dividend_low_vol/RUNBOOK.md)。

## 安装与运行

### 行情看板

```bash
source .venv/bin/activate
python -m pip install -e '.[dashboard]'
mtp viewer
```

安装一次后，在已激活该 Python 环境的任意目录均可运行：

```bash
mtp viewer                         # 默认沪深 300
mtp viewer 600519                   # 股票
mtp viewer 510300                   # ETF
mtp viewer 050025                   # 场外基金
mtp viewer 000001 --type index      # 上证指数；同码股票用 --type stock
mtp viewer 161725 --type lof        # LOF
mtp viewer --port 8502              # 8501 已被占用时
mtp viewer --no-browser             # 不自动打开浏览器
mtp viewer --help
```

命令在前台运行，自动打开本机浏览器，按 `Ctrl+C` 停止。`--type` 支持
`stock/index/etf/lof/fund`。省略类型时按常见代码规则推测，存在同码或例外时需显式指定，
也可在页面重新选择；仅凭六位代码无法唯一识别所有市场的标的。
如果提示找不到 `mtp`，请先激活安装时的环境（本项目为 `source .venv/bin/activate`）。

看板界面默认使用浅色黑白灰主题；行情图保留红涨绿跌，六条均线通过不同颜色区分。
`mtp viewer` 从任意目录启动都会使用相同主题。

浏览器打开终端显示的本地地址（默认 `http://localhost:8501`）。选择标的类型并输入六位代码，
点击「查询行情」。支持 A 股、指数、ETF、LOF，以及场外基金单位净值。
默认加载沪深 300（000300），可切换全部、10 年、5 年、1 年；范围以最新可用数据日为终点，
历史不足时展示全部可用记录。数据源不一定覆盖上市或成立首日，页面显示实际起止日期。

MA5、MA10、MA20、MA30、MA60、MA120 按全部历史收盘价计算后截取显示区间，
可通过多选框移除或点击图例隐藏。支持缩放、成交量、原始数据查看和 CSV 下载。
股票、ETF、LOF 可选择不复权、前复权、后复权；场外基金没有 OHLC，展示单位净值曲线，
均线按净值记录计算。场外基金净值不含分红再投资，不代表总回报。

行情通过 AkShare 获取，内存缓存 1 小时，可手动刷新；单次请求超时 60 秒。
原始数据及来源记录位于 `~/.cache/my-trading-policy/dashboard/`（设置了 `XDG_CACHE_HOME` 时使用该目录）；
失败时显示错误，不以旧缓存冒充最新行情。
运行测试：`python -m unittest discover -s tests`（需安装 dashboard 可选依赖）。

需要 Python 3.10 或更新版本。在项目根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m trading_analysis.studies.csi300.run
```

可编辑安装后，修改 Python 源码通常无需重新安装。修改依赖或包配置后重新执行安装命令。
上述沪深300模块入口只输出就绪提示；红利低波快照入口见运行说明。

## 目录结构

```text
src/trading_analysis/
├── data/                 # 共用 AkShare 接口封装、缓存、数据口径
├── common/               # 共用计算、时间序列处理与绘图
└── studies/
    └── csi300/           # 沪深 300 分析骨架
        ├── data.py       # 模块数据组合与清洗
        ├── analysis.py   # 分析计算
        ├── charts.py     # 专属图表
        └── run.py        # 运行入口
notebooks/                # 探索笔记
tests/                   # 关键逻辑测试
data/raw/                # 原始数据文件（不提交 Git）
data/processed/          # 整理后数据（不提交 Git）
outputs/                 # 图表和报告（不提交 Git）
```

`src/trading_analysis/data/` 是 Python 代码，根目录 `data/` 是本地数据文件。

## 添加分析模块

在 `studies/` 中新建主题目录和 `__init__.py`，参考 `csi300/` 按需添加文件。
不同主题可以采用不同结构；仅标的参数不同时，优先复用同一模块。

共用函数定义好后，使用绝对导入，例如在 `common/returns.py` 实现
`cumulative_return` 后，分析模块可写：

```python
from trading_analysis.common.returns import cumulative_return
```

使用 `python -m trading_analysis.studies.<模块名>.run` 运行模块，避免修改 `sys.path`。

依赖方向为 `studies → common / data`；共用层不依赖具体分析模块。
数据获取、分析计算、可视化分开；导入模块时不触发联网或写文件。

## 数据约定

接入具体接口时记录日期与价格列名、类型、单位、复权方式、数据来源与获取时间。
缓存键应包含影响结果的参数；缓存刷新策略随数据接口实现。
新分析模块先保留自己的逻辑，出现真实重复后再提取共用能力。
