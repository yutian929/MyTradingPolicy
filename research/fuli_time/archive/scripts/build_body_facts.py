"""Human-structured factual observations from visible note bodies.

These are author-reported snapshots, not market-data recomputations. Percent
values use percentage units (4.21 means 4.21%, not 0.0421). Narrative is
paraphrased; absent values remain absent. Source discrepancies are preserved.
"""
from pathlib import Path
import csv,json

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'research/fuli_time/archive'
notes=json.loads((OUT/'source_manifest.json').read_text())
daily={n['date'][5:]:n for n in notes if n['note_type']=='daily'}
M={
'p':('price','原帖点位/价格','原帖未注明'),
'chg':('daily_return_pct','当日涨跌幅','%'),
'dy':('dividend_yield_pct','股息率','%'),
'cn':('bond_yield_10y_pct','中国10年期国债收益率','%'),
'sp':('equity_bond_spread_pp','股债利差','百分点'),
'spp':('spread_percentile','股债利差历史分位','百分位'),
'dyp':('dividend_yield_percentile','股息率历史分位','百分位'),
'pe':('pe_ttm','滚动市盈率','倍'),
'pep':('pe_percentile_10y','PE近10年历史分位','百分位'),
'pb':('pb','市净率','倍'),
'pbp':('pb_percentile_10y','PB近10年历史分位','百分位'),
'roe':('roe_pct','ROE','%'),
'bias':('bias_250_pct','250日年线偏离率','%'),
'rsi':('rsi14','RSI(14)','点'),
'j':('kdj_j','日线KDJ J','点'),
'k':('kdj_k','日线KDJ K','点'),
'r5':('return_5d_pct','近5日涨跌幅','%'),
'r10':('return_10d_pct','近10日涨跌幅','%'),
'r20':('return_20d_pct','近20日涨跌幅','%'),
'vol':('annualized_volatility_pct','年化波动率','%'),
'ratio':('volume_ratio','量比','倍'),
'streak':('streak','连阳/连阴天数（正/负）','天'),
'pos':('position_52w_pct','52周价格位置','%'),
'bb':('bollinger_percent_b_pct','布林带位置','%'),
'crowd':('crowding','拥挤度','点'),
'score':('score_body','综合评分（正文）','分'),
'precise':('score_precise','正文同时给出的精确评分','分'),
'grade':('score_grade','综合评级','级'),
'n':('same_score_samples','历史同分样本数','个'),
'avg':('forward_60d_mean_pct','未来60日收益均值','%'),
'med':('forward_60d_median_pct','未来60日收益中位数','%'),
'min':('forward_60d_min_pct','未来60日收益最低值','%'),
'max':('forward_60d_max_pct','未来60日收益最高值','%'),
}
# All values below were read in the browser; no imputation from images or APIs.
DATA='''09-01 p=1.204 chg=1.01 dy=4.24 cn=1.69 sp=2.55 spp=44 pe=8.54 pep=80 rsi=65 j=93.8 bias=2.49 pos=78 score=33.7 grade=D n=163 avg=2.45
09-02 p=1.202 chg=-0.50 dy=4.19 cn=1.68 sp=2.51 spp=42 pe=8.64 pep=80 rsi=62.6 j=84.5 bias=2.33 pos=77 score=37.9 grade=D
09-03 p=1.209 chg=0.67 dy=4.17 cn=1.69 sp=2.48 spp=41 pe=8.63 pep=80 rsi=64.8 j=84.4 bias=2.92 pos=81 score=30.6 grade=D
09-04 p=1.209 chg=0.75 dy=4.21 cn=1.68 sp=2.53 spp=44 bias=2.93 rsi=64.8 pos=81 r20=4.40 score=31 grade=D
09-07 p=1.190 chg=-1.41 dy=4.19 sp=2.51 spp=43 bias=1.32 pe=8.58 pep=80 pb=0.88 pbp=63 rsi=54.4 j=46.8 pos=70 score=57 grade=C
09-08 p=1.203 chg=0.67 dy=4.26 sp=2.58 spp=47 bias=2.42 rsi=60.1 j=61.3 pos=77 bb=78 pe=8.44 pb=0.86 score=40 grade=C
09-09 p=1.212 chg=0.41 dy=4.26 sp=2.58 spp=47 bias=3.18 pe=8.45 pep=78 pb=0.86 pbp=61 rsi=63.3 j=82.9 pos=82 bb=86 r20=4.57 score=30 grade=D
09-10 p=1.215 chg=0.33 dy=4.23 cn=1.68 sp=2.55 pe=8.49 pep=79 pb=0.87 pbp=62 bias=3.43 rsi=64.4 j=92.7 r5=1.25 r10=2.70 r20=5.01 streak=3 pos=84 score=27.7 grade=D
09-11 p=1.210 chg=-0.33 dy=4.27 cn=1.68 sp=2.59 pe=8.56 pep=79 pb=0.88 bias=3 rsi=61.5 j=81.5 pos=81 score=32.9 grade=D
09-14 p=1.207 chg=0.33 r5=1 r20=4.41 pe=8.55 pep=79 pb=0.88 pbp=63 dy=4.28 cn=1.69 sp=2.59 spp=43 bias=2.74 rsi=59.1 j=58.5 pos=80 score=38.1 grade=D avg=2.45 med=1.41
09-15 p=1.200 chg=-0.66 pe=8.59 pep=80 pb=0.88 pbp=63 dy=4.26 cn=1.69 sp=2.57 spp=42 bias=2.14 rsi=55 j=38.9 pos=76 r20=3.36 r5=-0.58 score=49.6 grade=C n=193 avg=3.14 med=1.67
09-16 p=1.191 chg=-0.42 bias=1.38 pos=70 j=14.4 rsi=50.4 dy=4.33 cn=1.69 sp=2.64 spp=44 pe=8.51 pep=79 pb=0.87 pbp=62 score=62 grade=B n=158 avg=3.84 med=2.92
09-17 p=1.188 chg=-0.17 dy=4.68 cn=1.69 sp=2.99 spp=44 pe=8.44 pep=77 pb=0.87 pbp=61 bias=1.12 rsi=49 j=5.7 pos=69 crowd=51.6 bb=30 score=67 grade=B n=158 avg=3.84 med=2.92
09-18 p=1.184 chg=0 dy=4.65 pe=8.43 pep=77 pb=0.86 pbp=61 sp=2.96 cn=1.69 spp=45 rsi=47.1 bias=0.78 j=-2.6 bb=19 pos=66 crowd=54.2 vol=11.3 score=72 grade=B n=191 avg=6.20 med=5.56
09-21 p=1.182 chg=-0.17 dy=4.44 dyp=60 cn=1.68 sp=2.76 spp=49 pe=8.37 bias=0.62 rsi=46.1 j=-1 bb=17 score=75 grade=B avg=6.20
09-22 p=1.184 chg=-0.17 dy=4.41 cn=1.68 sp=2.73 spp=47 pe=8.44 pep=77 pb=0.87 pbp=61 bias=0.79 rsi=47.1 j=8.9 r20=-0.08 pos=66 score=72 grade=B n=191 avg=6.20 med=5.56
09-23 p=1.181 chg=-0.51 dy=4.40 cn=1.68 sp=2.72 spp=47 pe=8.45 pep=78 pb=0.87 roe=10.26 bias=0.53 pos=65 r10=-2.48 bb=15 rsi=45.5 j=8.8 score=76 grade=B n=191 avg=6.20 med=5.56
09-24 p=1.186 chg=0.34 dy=4.42 cn=1.68 sp=2.74 spp=48 pe=8.39 pep=76 pb=0.86 pbp=60 bias=0.96 rsi=48.6 j=18.9 pos=68 crowd=51.6 bb=26 score=69 grade=B n=158 avg=3.84 med=2.92
09-28 p=1.182 chg=-0.25 dy=4.45 cn=1.67 sp=2.78 spp=47 pe=8.45 pep=78 bias=0.62 pos=65 rsi=46.1 j=16.7 bb=17 score=74 grade=B avg=6.20 min=-8.72 max=28.02
09-29 p=1.181 chg=0.08 dy=4.42 cn=1.68 sp=2.74 spp=45 pe=8.48 pep=78 pb=0.87 pbp=62 bias=0.53 rsi=45.7 j=17.1 r10=-2.24 r20=-0.92 vol=10 pos=65 bb=18 crowd=49.8 score=75.2 grade=B avg=6.20 med=5.56 min=-8.72 max=28.02
09-30 p=1.195 chg=1.27 dy=4.41 pe=8.49 pep=78 pb=0.87 pbp=62 sp=2.74 cn=1.67 spp=46 bias=1.71 pos=73 r5=0.67 r10=-0.08 r20=-1.08 rsi=54.7 j=77.7 vol=9.8 score=54 precise=53.9 grade=C n=183 avg=3.72 med=2.82 max=21.03 min=-9.90
10-08 p=1.209 chg=1.09 dy=4.39 cn=1.68 sp=2.71 spp=43 pe=8.55 pep=79 pb=0.88 pbp=64 bias=2.88 rsi=61.4 j=100.4 pos=81 score=33 grade=D n=163 avg=2.45 max=18.45 min=-6.85
10-09 p=1.216 chg=0.33 pe=8.65 pep=80 pb=0.89 pbp=65 j=117.1 bb=90 pos=85 dy=4.34 sp=2.65 spp=40 bias=3.46 score=25 grade=D n=166 avg=1.31 med=-0.43 min=-6.98 max=14.96
10-12 p=1.224 chg=1.32 bias=4.12 dy=4.37 cn=1.69 sp=2.69 spp=42 pe=8.59 pep=80 pbp=64 j=110.1 k=75.5 pos=89 bb=101 rsi=66.2 score=19 grade=E avg=0.15
10-13 p=1.227 chg=-0.24 bias=4.34 dy=4.26 cn=1.67 sp=2.59 spp=38 pe=8.79 pep=80 pos=91 bb=96 rsi=66.1 j=114.2 score=19 grade=E n=153 avg=0.15 med=0 min=-9.36
10-14 p=1.232 chg=0.65 bias=4.74 dy=4.24 cn=1.67 sp=2.58 j=106.5 rsi=66.9 bb=98 pos=94 score=15 grade=E
10-15 p=1.210 chg=-1.71 pe=8.87 pep=80 dy=4.23 cn=1.65 sp=2.58 rsi=54.9 j=75.3 bias=2.85 pos=81 score=39 grade=D
10-16 p=1.221 chg=0.74 pe=8.89 pep=80 dy=4.22 sp=2.56 spp=37 bias=3.76 pos=88 bb=80 rsi=59.2 score=28 grade=D avg=1.31 med=0.09 max=11.45 min=-5.72
10-19 p=1.233 chg=1.15 pos=94 bb=92 j=85.7 bias=4.75 dy=4.20 sp=2.55 score=17 grade=E
10-26 p=1.204 chg=0.25 dy=4.78 cn=1.64 sp=3.14 spp=37 bias=2.19 rsi=49.7 j=13.2 pe=8.78 pep=80 pos=78 r5=-2.59 r20=1.69 ratio=1 score=52 grade=C n=183 avg=3.72
10-27 p=1.222 chg=0.74 pe=8.99 pep=80 dy=4.60 cn=1.64 sp=2.96 spp=35 bias=3.70 rsi=56.6 pos=88 streak=2 ratio=1.06 score=32 grade=D med=1.41
10-28 p=1.212 chg=-0.82 pe=9.04 pep=80 dy=4.61 cn=1.63 sp=2.98 spp=34 bias=2.84 pos=82 rsi=52.2 score=43 grade=C n=193 avg=3.14
10-29 p=1.232 chg=0.98 bias=4.52 pos=94 bb=80 sp=2.99 spp=34 pe=9.01 pep=80 dy=4.62 rsi=59.1 j=76.6 grade=D
10-30 p=1.237 chg=0.08 dy=4.52 cn=1.62 sp=2.9 spp=30 pe=9.38 pb=0.94 pos=97 bias=4.93 j=97.4 rsi=60.6 bb=85 score=16 grade=E n=153 avg=0.15
11-02 p=1.239 chg=-0.32 dy=4.51 cn=1.65 sp=2.86 spp=29 pe=9.38 pep=80 bias=5.08 rsi=61 j=93.9 pos=98 bb=83 score=16 grade=E
11-03 p=1.230 chg=-0.57 pe=9.26 pep=80 pb=0.93 dy=4.53 cn=1.63 sp=2.90 spp=32 rsi=56.6 bias=4.30 pos=93 streak=-2 score=28 grade=D
11-04 p=1.242 chg=0.32 dy=4.54 sp=2.92 spp=33 pe=9.21 pep=80 bias=5.30 r5=1.80 r20=3.85 ratio=1.08 streak=2 bb=86 rsi=61.8 j=88.2 pos=99 score=15 grade=E
11-05 p=1.218 chg=-1.14 pe=9.04 pep=80 dy=4.62 sp=3.01 cn=1.61 spp=34 rsi=50.5 bias=3.26 pos=86 j=51.4 score=41 grade=C n=193 avg=3.14 med=1.67
11-06 p=1.229 chg=0.66 pe=8.89 pep=80 dy=4.70 cn=1.60 sp=3.10 spp=37 rsi=55.1 bias=4.19 j=46.4 pos=92 score=32 grade=D n=166 avg=2.46'''
facts=[]
def add(date,metric,value,unit,summary,subject='中证红利低波（正文称谓）',note=None):
    note=note or daily[date]
    facts.append(dict(date=note['date'],note_id=note['note_id'],subject=subject,metric=metric,value=value,unit=unit,summary=summary,source_url=note['url'],source_channel='body',verification='read_from_browser'))
for line in DATA.splitlines():
    date,*tokens=line.split()
    for token in tokens:
        key,val=token.split('=')
        metric,label,unit=M[key]
        value=val if key=='grade' else float(val)
        if isinstance(value,float) and value.is_integer(): value=int(value)
        if key=='sp' and date in ['10-12','10-14']:
            label+='；正文给出的股息率与国债收益率相减和此值不一致，保留原值'
        add(date,metric,value,unit,label)
    add(date,'data_cutoff_time','11:30','Asia/Shanghai','正文声明的数据截止时间；不等同于全天收盘')
    if any(t.split('=')[0] in ('avg','med','min','max') for t in tokens):
        add(date,'forward_horizon_days_reported',60,'日/天','同分样本的未来收益观察期；正文用60天、60日或60交易日，尚未逐条确认交易日口径')

# Explicit actions and personal rules, paraphrased independently of chart labels.
ACTIONS={
'09-01':'谨慎买入；注意止盈','09-02':'谨慎买入','09-03':'谨慎买入；注意止盈','09-04':'谨慎买入',
'09-07':'等待A级再考虑进场','09-09':'减仓','09-10':'减仓，避免追涨',
'09-11':'谨慎买入','09-15':'持有观望','09-16':'等待A级','09-17':'等待A级','09-18':'等待A级',
'09-21':'等待A级','09-22':'等待A级','09-23':'等待A级','09-28':'中证红利低波继续等待A级',
'09-30':'中性位置','10-08':'随上涨逐步卖出',
'10-09':'减仓或谨慎操作','10-12':'减仓、止盈控仓','10-13':'减仓',
'10-14':'减仓、止盈控仓','10-15':'谨慎买入','10-16':'减仓、谨慎追高',
'10-19':'止盈控仓、适当减仓','10-26':'持有观望','10-27':'谨慎买入，避免重仓追高',
'10-28':'谨慎买入或保持中性','10-29':'考虑减仓','10-30':'减仓',
'11-02':'减仓','11-04':'减仓','11-05':'谨慎买入','11-06':'谨慎买入',
}
for date,value in ACTIONS.items():
    add(date,'author_action',value,'','作者操作倾向的简洁转述，不据此改写评分')
    if date in ['09-07','10-08']:
        facts[-1]['source_channel']='title'
for date,s100,s50 in [('10-12','C','E'),('10-13','C','E'),('10-14','C','E'),('10-16','C','E'),('10-28','B','C'),('10-29','B','C'),('10-30','C','E'),('11-02','D','E'),('11-03','D','E'),('11-04','D','E'),('11-05','C','D'),('11-06','D','E')]:
    add(date,'score_grade',s100,'级','正文列示的其他标的评级',subject='红利低波100')
    add(date,'score_grade',s50,'级','正文列示的其他标的评级',subject='红利低波50' if date=='10-12' else '南方50')
add('10-28','score_body',68.6,'分','正文列示的其他标的评分',subject='红利低波100')
add('10-28','score_body',46,'分','正文列示的其他标的评分',subject='南方50')
for subject in ['红利低波100','南方50']:
    add('10-27','author_action','不在合适补仓区间','','正文对其他标的的简洁判断',subject=subject)
for subject in ['红利低波50','红利低波100']:
    add('09-28','author_action','已进入性价比区间','','正文对其他标的的简洁判断',subject=subject)
for date,subject,value in [('10-16','红利低波100','观望'),('10-16','南方50','减仓'),('11-05','红利低波100','谨慎买入'),('11-05','南方50','谨慎买入'),('11-06','红利低波100','谨慎买入'),('11-06','南方50','减仓')]:
    add(date,'author_action',value,'','正文对其他标的操作倾向的简洁转述',subject=subject)

add('09-04','personal_dividend_threshold_pct',5,'%','个人入场规则之一：股息率超过5%；与下一条件间原帖使用斜线，未明确AND/OR')
add('09-04','personal_dividend_treasury_ratio_threshold',3,'倍','个人入场规则之一：股息为国债3倍；原帖未明确两个收益条件的逻辑关系')
add('09-04','desired_yield_spread_min_pp',3,'百分点','作者期望的股债利差范围下界')
add('09-04','desired_yield_spread_max_pp',4,'百分点','作者期望的股债利差范围上界')
add('09-04','dividend_treasury_ratio_reported',2.53,'倍','原帖声称倍数；4.21÷1.68≈2.506，与2.53不一致，保留作者原数')
add('09-04','personal_weekly_entry_rule','周K处于布林带中下轨，RSI与KDJ同时超卖','','作者个人周线入场条件，未给出全部具体阈值')
add('09-04','personal_entry_conditions_met',False,'','作者称当前三个入场条件均未满足')
add('09-14','weekly_kdj_j',96.39,'点','周线KDJ J，不能与日线J合并')
add('09-14','suggested_position_min_pct',50,'%','作者建议仓位范围下界：五成')
add('09-14','suggested_position_max_pct',60,'%','作者建议仓位范围上界：六成')
add('09-14','price_vs_ma5','略低于MA5','','正文日K位置描述')
add('09-14','weekly_bollinger_position','接近上轨','','正文周布林带位置描述，无精确数值')
add('09-30','long_term_volatility_reference_min_pct',8,'%','作者给出的长期年化波动参考范围下界')
add('09-30','long_term_volatility_reference_max_pct',15,'%','作者给出的长期年化波动参考范围上界')
add('09-30','attached_other_instruments','南方50、红利低波100','','正文称附件包含这些标的；是否有对应图由图片索引独立核对')
add('10-19','risk_score_threshold',25,'分','正文称评分低于25时应留意回调；严格小于')
add('10-19','score_scale_max',100,'分','正文写作17/100')
add('10-29','backtest_time_description','近60个交易日','','作者正文对历史同分样本时间的描述；未直接等同于未来60日收益期限')

notice_summaries={
'6a97b6d7000000002a0257db':'作者报告内容阅读量已超过100万，回顾持续发布红利低波分析；无当天指标更新。',
'6ad6f0ad000000002a00d12b':'作者称将优化升级模型，完成前暂停更新。',
'6ad83e820000000033020718':'作者称旧电脑出现问题，已购买新电脑，部署调试后恢复更新。',
}
for note in notes:
    if note['note_id'] in notice_summaries:
        add(note['date'][5:],'note_summary',notice_summaries[note['note_id']],'','非日报说明的简洁转述',subject='作者更新说明',note=note)
        if note['note_id']=='6a97b6d7000000002a0257db':
            add('09-02','content_reads_lower_bound',1000000,'次','作者报告阅读量超过此数值',subject='内容阅读量',note=note)

facts.sort(key=lambda r:(r['date'],r['note_id'],r['subject'],r['metric']))
assert len(daily)==39
assert len({(r['note_id'],r['subject'],r['metric']) for r in facts})==len(facts)
(OUT/'body_facts.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n')
with (OUT/'body_facts.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(facts[0]));writer.writeheader();writer.writerows(facts)
print({'body_facts':len(facts),'notes':len(set(r['note_id'] for r in facts)),'daily':len(daily)})
