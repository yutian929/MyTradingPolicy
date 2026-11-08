复利时光公开指标归档
范围：2026-09-01 至 2026-11-08；当前可见最新笔记 2026-11-06。

这份归档记录作者发布了什么，用于后续研究；不是重新计算出来的行情或已复现的策略结果。
主页覆盖核对见 coverage.json，逐篇来源见 source_manifest.json。
42篇笔记包括39篇指标日报、3篇说明，共274张原图。10月19日原帖只有6张图，其余日报均7张。

主要使用入口
1. outputs/fuli_time_archive/ 下的 Excel：按日期筛选每日指标，查看全部图中指标、正文补充、收益分布与提取问题。
2. all_observations.csv / .json：统一长表，保留 source_channel，适合 pandas 分析。
   daily_indicators.csv / .json：39日报的图片指标宽表；百分数仍为展示单位，字段说明见 metric_catalog.csv。
3. notes_text/：每篇一个文本文件，正文事实摘要与图片OCR文字分别列出。
4. image_metrics.csv、body_facts.csv、histogram_bins.csv：分来源的结构化表格。
5. data/raw/fuli_time_archive/<笔记ID>/：原图；以SHA256命名，可回查每个数值。
6. research/fuli_time/archive/ocr/、ocr_details/：全页和局部OCR，含置信度、坐标、文字。
7. numeric_line_inventory.json：图中包含数字的行，包括尚未映射到独立指标的轴标签、阈值等。
8. extraction_quality.json、body_image_audit.json：解析遗漏、跨页差异、图文差异和样本数核对。

数值口径
- 百分数按展示单位保存：4.21 表示4.21%，并非0.0421；利差用百分点。
- 分位数45表示第45百分位；量比与PE/PB是倍数；连续涨跌以正数表示涨、负数表示跌。
- 正文数据一般截止11:30，不能默认是当日15:00收盘。
- 估值页另列PE/PB/DY数据日期，不强行改成发帖日期。
- price保留图上原价，源图未明确货币或证券代码；不能把“中证红利低波”的名称直接等同于已确认ETF代码。
- body、title、image分别保留。评分取整值与精确值分别保存；不取平均、不用本地计算覆盖作者原数。
- 其他标的的正文评级独立记录，不混入主标的每日数值。
- 空值表示来源未出现或尚未可靠提取，不能当作0；没有笔记的日期不补数据。

质量边界
- machine_ocr_unverified 表示机器识别，不是逐字人工核验；置信度高不保证符号正确。
- 图文匹配是交叉佐证，差异候选仍需回看原图。作者原文有算术、评级或图文差异时保留原值。
- 9月30日正文称附南方50和红利低波100图，但当前可见七张图均为主标的；不虚构附图。
- 曲线没有标注的逐日点位没有被当作原始时序提取。已保存曲线原图和标注，未来若需数字化须单独估计并标注误差。
- 当前覆盖主页可见笔记，不包含隐藏/删除内容，也没有穷尽评论区。说明性正文以事实摘要整理。

增量与复查
所有数据处理脚本位于 research/fuli_time/archive/scripts/，只读取显式清单，不访问小红书网络接口。
ocr_images.py 依赖 rapidocr-onnxruntime、Pillow；OCR按图片SHA256缓存，重复运行可复用。
在仓库根目录用 .venv/bin/python 运行 OCR -> ocr_details.py -> extract_metrics.py ->
build_body_facts.py -> audit_body_image.py -> export_archive.py。
build_manifest.py 使用本机浏览器下载目录中的明确文件前缀，只适合本次采集重建。
build_workbook.mjs 使用本机捆绑的 @oai/artifact-tool；请按脚本参数和环境重新生成。
ZIP中的路径相对仓库根目录保留，解压后可按相同相对路径回查证据。
