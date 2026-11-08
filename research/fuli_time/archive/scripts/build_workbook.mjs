import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

// Run after extraction finishes. This builder does not fetch network data.
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..');
const DATA = path.join(ROOT, 'research/fuli_time/archive');
const OUT = path.join(ROOT, 'outputs/fuli_time_archive');
const read = async (name, fallback) => {
  try { return JSON.parse(await fs.readFile(path.join(DATA, name), 'utf8')); }
  catch (e) { if (e.code === 'ENOENT' && fallback !== undefined) return fallback; throw e; }
};
const manifest = await read('source_manifest.json');
const data = await read('metrics_long.json');
const imageIndex = await read('ocr_index.json');
const histogramData = await read('histograms.json');
const bodyData = await read('body_facts.json', []);
const labelData = await read('metric_dictionary.json', {});
const auditData = await read('body_image_audit.json', {differences:[]});
const extractionQuality = await read('extraction_quality.json', {anomalies:[]});
const notes = (Array.isArray(manifest) ? manifest : manifest.notes).sort((a,b)=>a.date.localeCompare(b.date));
const observations = [...data.observations].sort((a,b)=>a.date.localeCompare(b.date)||a.note_id.localeCompare(b.note_id)||a.page_kind.localeCompare(b.page_kind)||a.metric.localeCompare(b.metric));
const body = Array.isArray(bodyData) ? bodyData : (bodyData.facts || bodyData.observations || bodyData.rows || []);
const images = imageIndex.images || [];
const histograms = histogramData.histograms || [];
const issues = data.missing_or_ambiguous || [];
const url = id => `https://www.xiaohongshu.com/explore/${id}`;
const kindLabels = {cover:'封面', overview:'总览', strength:'强弱', price:'走势', value:'估值', score:'评分', position:'位置', other:'其他'};
const defaults = {
  price:'价格',daily_return_pct:'当日涨跌',score_rounded:'综合评分（整分）',score_precise:'综合评分（精确）',score_grade:'综合评级',
  bias_250_pct:'年线乖离率',rsi14:'RSI(14)',dividend_yield_pct:'股息率',bond_yield_10y_pct:'10年期国债收益率',equity_bond_spread_pp:'股债利差',spread_percentile:'利差历史分位',
  pe_ttm:'滚动PE',pb:'PB',pe_percentile_10y:'PE近10年分位',pb_percentile_10y:'PB近10年分位',roe_pct:'ROE',
  kdj_k:'KDJ K',kdj_d:'KDJ D',kdj_j:'KDJ J',return_5d_pct:'近5日收益',return_10d_pct:'近10日收益',return_20d_pct:'近20日收益',
  annualized_volatility_20d_pct:'20日年化波动率',volume_ratio:'量比',position_52w_pct:'52周位置',bollinger_percent_b_pct:'布林带位置',crowding:'拥挤度',streak:'连续涨跌天数',
  same_score_samples:'同分样本数',forward_60d_mean_pct:'后60日收益均值',forward_60d_median_pct:'后60日收益中位数',forward_60d_min_pct:'后60日收益最小值',forward_60d_max_pct:'后60日收益最大值',
  spread_historical_mean_pp:'利差历史均值',spread_historical_min_pp:'利差历史最小值',spread_historical_max_pp:'利差历史最大值',
  valuation_date_pe:'PE估值日期',valuation_date_pb:'PB估值日期',valuation_date_dy:'股息率估值日期',data_capture_time:'图中取数时间',
  bias_action_text:'年线操作提示',bias_sentiment_text:'年线状态',rsi_action_text:'RSI操作提示',rsi_sentiment_text:'RSI状态',score_action_text:'评分操作提示',
};
function label(key) { const x=labelData[key] || labelData.metrics?.[key]; return typeof x==='string'?x:(x?.label || x?.name_zh || x?.label_zh || defaults[key] || key); }
function col(i) { let s=''; do {s=String.fromCharCode(65+i%26)+s;i=Math.floor(i/26)-1;} while(i>=0);return s; }
function date(d) { return d && /^\d{4}-\d{2}-\d{2}$/.test(d)?new Date(`${d}T00:00:00Z`):d||null; }
function typed(value, unit) { return unit==='date'?date(value):(typeof value==='number'&&unit==='%'?value/100:value??null); }
function fmt(unit) { return ({'%':'0.00%','date':'yyyy-mm-dd','days':'0','percentile':'0.0','source_quote':'0.000','source_price_unit_unknown':'0.000','CNY':'0.000','multiple':'0.00','index':'0.0','score':'0.0','pp':'0.000'})[unit] || 'General'; }
function quality(o) { return o.status==='source_not_reported'?'原图未报告数值':o.status==='visually_verified'?'已目视核验':o.status==='manual_verified'?'已人工核验':o.status==='machine_ocr_unverified'?'OCR待逐项核验':o.status||''; }
function unitLabel(unit) {return ({source_price_unit_unknown:'原图未注明',source_quote:'原图未注明',CNY:'元',score:'分',index:'指数值',multiple:'倍',percentile:'百分位',days:'天',date:'日期',text:'文本',grade:'评级',pp:'百分点'})[unit]||unit||'';}
function fitTextColumns(sheetName, rows, widths, columns) {
 const s=sheets[sheetName];
 for(const c of columns) if(rows.length)s.getRange(`${col(c)}6:${col(c)}${rows.length+5}`).format.wrapText=true;
 rows.forEach((r,i)=>{
   let lines=1;
   for(const c of columns) {
     const text=String(r[c]??'');
     const visualLength=[...text].reduce((n,ch)=>n+(/[\u2e80-\uffef]/.test(ch)?2:1),0);
     lines=Math.max(lines,Math.ceil(visualLength/(widths[c]-2)));
   }
   if(lines>1)s.getRange(`A${i+6}:${col(widths.length-1)}${i+6}`).format.rowHeight=lines*15+6;
 });
}
const wb = Workbook.create();
const sheets = {};
const checks = [];

function table(name, title, context, headers, rows, widths, formats={}, previewCols=8) {
  const s=wb.worksheets.add(name);sheets[name]=s;s.showGridLines=false;
  const last=col(headers.length-1);const end=rows.length+5;
  s.getRange(`A1:${last}${Math.max(end,8)}`).format.font={name:'Arial',size:10,color:'#202D3A'};
  s.getRange(`A1:${last}${Math.max(end,8)}`).format.verticalAlignment='center';
  s.getRange('A2').values=[[title]];s.getRange('A2').format.font={name:'Arial',size:14,bold:true,color:'#17324D'};
  s.getRange(`A2:${col(Math.min(headers.length-1,7))}2`).format.borders={bottom:{style:'thin',color:'#A8B6C5'}};
  s.getRange('A3').values=[[context]];s.getRange('A3').format.font={name:'Arial',size:10,italic:true,color:'#596A7B'};
  s.getRange(`A5:${last}5`).values=[headers];
  s.getRange(`A5:${last}5`).format={fill:'#234A69',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},wrapText:true,horizontalAlignment:'center',verticalAlignment:'center',rowHeight:34};
  if(rows.length) {
    s.getRange(`A6:${last}${end}`).values=rows;
    s.getRange(`A6:${last}${end}`).format.rowHeight=22;
    s.getRange(`A6:${last}${end}`).format.wrapText=false;
    const t=s.tables.add(`A5:${last}${end}`,true,`ArchiveTable${Object.keys(sheets).length}`);t.showFilterButton=true;
  }
  widths.forEach((w,i)=>{s.getRange(`${col(i)}1:${col(i)}${Math.max(end,8)}`).format.columnWidth=w;});
  for(const [i,format] of Object.entries(formats)) if(rows.length)s.getRange(`${col(+i)}6:${col(+i)}${end}`).setNumberFormat(format);
  s.freezePanes.freezeRows(5);s.freezePanes.freezeColumns(Math.min(2,headers.length));
  checks.push({name,rows:rows.length,cols:headers.length,previewRange:`A1:${col(Math.min(headers.length-1,previewCols-1))}${Math.min(end,14)}`});
  return s;
}

// One canonical source observation per row. Daily view points to these cells.
const metricRows=observations.map(o=>[date(o.date),o.instrument_name||'标的待核实',kindLabels[o.page_kind]||o.page_kind,label(o.metric),typed(o.value,o.unit),unitLabel(o.unit),date(o.chart_date),o.metric,quality(o),o.confidence??null,o.raw_text||'',o.note_id,o.image_file,o.line_id==null?'':String(o.line_id),'',url(o.note_id)]);
const priority={price:['cover','overview'],daily_return_pct:['cover','overview'],score_grade:['score','cover','overview'],score_rounded:['cover','overview'],score_precise:['score'],bias_250_pct:['strength','cover','overview'],rsi14:['strength','cover','overview'],dividend_yield_pct:['value','cover','overview'],equity_bond_spread_pp:['value','overview'],spread_percentile:['value','overview']};
const dailyKeys=['price','daily_return_pct','score_precise','score_rounded','score_grade','score_action_text','bias_250_pct','rsi14','kdj_k','kdj_d','kdj_j','dividend_yield_pct','bond_yield_10y_pct','equity_bond_spread_pp','spread_percentile','pe_ttm','pe_percentile_10y','pb','pb_percentile_10y','roe_pct','return_5d_pct','return_10d_pct','return_20d_pct','annualized_volatility_20d_pct','volume_ratio','position_52w_pct','bollinger_percent_b_pct','crowding','streak','same_score_samples','forward_60d_mean_pct','forward_60d_median_pct','forward_60d_min_pct','forward_60d_max_pct','valuation_date_pe','data_capture_time'];
const dailyNotes=notes.flatMap(n=>[...new Set(observations.filter(o=>o.note_id===(n.note_id||n.id)).map(o=>JSON.stringify([o.instrument_name||null,o.chart_date||null])))].map(key=>{const [instrument_name,chart_date]=JSON.parse(key);return {...n,instrument_name,chart_date};}));
const selected=[];
const dailyRows=dailyNotes.map(n=> {
 const id=n.note_id||n.id;
 const matches=dailyKeys.map(k=>observations.map((o,i)=>({o,i})).filter(x=>x.o.note_id===id&&(x.o.instrument_name||null)===n.instrument_name&&(x.o.chart_date||null)===n.chart_date&&x.o.metric===k&&x.o.value!==null&&x.o.value!==undefined).sort((a,b)=>{
 const pref=priority[k]||(['pe_ttm','pb','roe_pct','bond_yield_10y_pct'].includes(k)?['value']:k.startsWith('kdj_')?['strength']:k.startsWith('return_')?['price']:k.startsWith('forward_')||k==='same_score_samples'?['score']:['position','value','strength','score','overview','cover']);
 const rank=o=>pref.includes(o.page_kind)?pref.indexOf(o.page_kind):99;
 return rank(a.o)-rank(b.o)||(b.o.confidence||0)-(a.o.confidence||0);
 })[0]); selected.push(matches);
 return [date(n.date),n.instrument_name||'标的待核实',date(n.chart_date),id,...matches.map(m=>m?typed(m.o.value,m.o.unit):null)];
});
const dailyHeaders=['笔记日期','图中标的','图中日期','笔记ID',...dailyKeys.map(k=>defaults[k]||label(k))];
const dailyFormats={0:'yyyy-mm-dd',2:'yyyy-mm-dd'};dailyKeys.forEach((k,i)=>{let o=observations.find(o=>o.metric===k);if(o)dailyFormats[i+4]=fmt(o.unit);});
table('每日指标','复利时光每日指标','2026-09-01起；按笔记、标的及图中日期分组。空白为未提取到。OCR值待逐项核验，整分与精确分分别保留。',dailyHeaders,dailyRows,[14,24,14,29,...dailyKeys.map(k=>/text|time/.test(k)?28:18)],dailyFormats,8).tabColor='#17324D';
table('图中全部指标','图中指标原始观察','同一指标在不同图页出现时分别记录；百分数显示为百分比，利差单位为百分点。',
 ['笔记日期','图中标的','图页','指标','数值或文本','单位','图中日期','指标键','核验状态','OCR置信度','识别原文','笔记ID','本地原图','OCR行号','','来源链接'],metricRows,[14,24,12,45,32,12,14,34,24,15,52,29,75,18,3,75],{0:'yyyy-mm-dd',6:'yyyy-mm-dd',9:'0.0%'},7);
observations.forEach((o,i)=>sheets['图中全部指标'].getRange(`E${i+6}`).setNumberFormat(fmt(o.unit)));
fitTextColumns('图中全部指标',metricRows,[14,24,12,45,32,12,14,34,24,15,52,29,75,18,3,75],[1,3,4,10]);
selected.forEach((row,i)=>row.forEach((x,j)=>{if(x)sheets['每日指标'].getRange(`${col(j+4)}${i+6}`).formulas=[[`='图中全部指标'!E${x.i+6}`]];}));

const noteRows=notes.map(n=>{
 const id=n.note_id||n.id;const imgs=images.filter(x=>x.note_id===id);const os=observations.filter(x=>x.note_id===id);
 return [date(n.date),n.title,id,n.expected_images??n.files?.length??null,imgs.length,os.length,[...new Set(imgs.map(x=>kindLabels[x.page_kind]||x.page_kind))].join('、'),n.note_type||n.kind||'',n.summary||n.coverage_note||'', '',n.url||url(id)];
});
table('笔记目录','笔记与采集范围','按主页可见笔记建立目录；没有日更的日期不补造数据。每篇链接可回到原始发布内容。',
 ['日期','标题','笔记ID','预期图片数','已存图片数','图中指标条数','已识别图页','类型','备注','','来源链接'],noteRows,[14,55,29,15,15,17,50,20,70,3,75],{0:'yyyy-mm-dd',3:'0',4:'0',5:'0'},6);
const bodyRows=body.map(o=>[date(o.date),o.subject||o.asset||'',o.summary||o.label||o.metric||'',typed(o.value,o.unit),unitLabel(o.unit),o.source_channel==='title'?'标题':'正文',o.metric||'',o.verification==='read_from_browser'?'浏览器已读取':o.verification||o.status||'',o.note_id||o.id||'','',o.source_url||url(o.note_id||o.id)]);
table('正文补充','正文指标与操作规则','正文事实单独保留，用于记录周线指标、其他标的评级、仓位及作者公开规则。',
 ['日期','标的或范围','指标或规则说明','数值或文本','单位','文字来源','指标键','记录状态','笔记ID','','来源链接'],bodyRows,[14,24,58,30,12,12,40,24,29,3,75],{0:'yyyy-mm-dd'},5);
body.forEach((o,i)=>sheets['正文补充'].getRange(`D${i+6}`).setNumberFormat(fmt(o.unit)));
fitTextColumns('正文补充',bodyRows,[14,24,58,30,12,12,40,24,29,3,75],[1,2,3]);
const histRows=histograms.flatMap(h=>h.bins.map(b=>[date(h.date),h.instrument_name||'标的待核实',b.ordinal,b.range_text_verified??b.range_raw??'',b.lower_pct==null?null:b.lower_pct/100,b.upper_pct==null?null:b.upper_pct/100,b.count??null,h.count_sum??null,quality(b.status?b:h),b.count_line?.confidence??null,h.note_id,h.image_file,'research/fuli_time/archive/histograms.json',url(h.note_id)]));
table('收益分布','历史同分样本的后60日收益分布','优先展示逐图目视核验的区间及柱计数。原始机器识别保存在histograms.json的previous_ocr_bins中。',
 ['日期','图中标的','分箱序号','收益区间','收益区间下界','收益区间上界','样本计数','本图计数合计','核验状态','计数OCR置信度','笔记ID','本地原图','原始OCR档案','来源链接'],histRows,[14,24,14,30,18,18,15,23,28,19,29,75,65,75],{0:'yyyy-mm-dd',2:'0',4:'0.00%',5:'0.00%',6:'0',7:'0',9:'0.0%'},7);
const issueRows=issues.map(o=>[date(o.date),o.note_id||'',kindLabels[o.page_kind]||o.page_kind||'',o.metric?label(o.metric):'',o.reason||o.issue||o.status||JSON.stringify(o),o.image_file||'','',o.note_id?url(o.note_id):'']);
for(const f of imageIndex.failures||[])issueRows.push([null,f.note_id||'','图片','OCR失败',f.error||'',f.source_file||'','',url(f.note_id)]);
for(const o of observations.filter(o=>o.status==='source_not_reported'))issueRows.push([date(o.date),o.note_id,kindLabels[o.page_kind]||o.page_kind,label(o.metric),'原图以破折号表示，未报告数值；汇总保留空白，不填0。',o.image_file,'',url(o.note_id)]);
for(const d of auditData.differences||[])issueRows.push([date(d.date),d.note_id||'',d.status==='confirmed_source_disagreement'?'已确认图文差异':'图文差异候选',label(d.metric),`正文：${d.body_value}；图片：${(d.image_values||[]).join('、')}。${d.meaning||d.status||'待核对'}`,(d.images||[]).join('\n'),'',d.source_url||url(d.note_id)]);
for(const a of extractionQuality.anomalies||[]) {
 const sourceNote=notes.find(n=>(n.note_id||n.id)===a.note_id || (!a.note_id&&n.date===a.date));
 const id=a.note_id||sourceNote?.note_id||sourceNote?.id||'';
 const meanings={
  body_attachment_claim_not_observed:a.note,
  cross_page_numeric_disagreement:`不同图页数值不一致：${(a.values||[]).map(v=>`${kindLabels[v.page_kind]||v.page_kind} ${v.value}`).join('；')}。保留各原值。`,
  grade_differs_from_printed_common_thresholds:`按通用阈值推得${a.expected_by_thresholds}级，与图中评级存在差异。保留原图评级，待核对当页阈值。`,
  histogram_bin_boundaries_unresolved:'直方图区间边界未全部可靠识别。原图与原文保留，不自动补负号。',
  histogram_count_incomplete_or_mismatch:`识别柱数${a.count_count??'未知'}，计数合计${a.count_sum??'未知'}，图中同分样本数${(a.sample_values||[]).join('、')}；待核验。`,
 };
 const types={body_attachment_claim_not_observed:'正文附件未见',cross_page_numeric_disagreement:'跨图数值差异',grade_differs_from_printed_common_thresholds:'评分评级不一致',histogram_bin_boundaries_unresolved:'分箱边界待核验',histogram_count_incomplete_or_mismatch:'柱计数待核验'};
 issueRows.push([date(a.date||sourceNote?.date),id,types[a.type]||a.type,a.metric?label(a.metric):'',meanings[a.type]||a.note||a.status||'',a.image_file||[...new Set((a.values||[]).map(v=>v.image_file).filter(Boolean))].join('\n'),'',id?url(id):'']);
}
table('提取问题','缺失与待核验项目','这是OCR提取问题清单，不代表其他机器识别值均已正确。原图、完整OCR文字和来源均保存在本地档案。',
 ['日期','笔记ID','图页','指标','问题说明','本地图片','','来源链接'],issueRows,[14,29,14,30,95,75,3,75],{0:'yyyy-mm-dd'},5);
fitTextColumns('提取问题',issueRows,[14,29,14,30,95,75,3,75],[3,4]);
await fs.mkdir(path.join(OUT,'previews'),{recursive:true});
wb.recalculate();
for(const c of checks) {
 const inspected=await wb.inspect({kind:'table',range:`'${c.name}'!A5:${col(Math.min(c.cols-1,5))}${Math.min(c.rows+5,8)}`,include:'values,formulas',tableMaxRows:4,tableMaxCols:6,maxChars:2200});
 await fs.writeFile(path.join(OUT,'previews',`${c.name}.inspect.ndjson`),inspected.ndjson);
 const png=await wb.render({sheetName:c.name,range:c.previewRange,scale:1.5,format:'png'});
 await fs.writeFile(path.join(OUT,'previews',`${c.name}.png`),new Uint8Array(await png.arrayBuffer()));
 console.log(JSON.stringify({sheet:c.name,rows:c.rows,cols:c.cols,rendered:true}));
}
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:30},maxChars:3000});
await fs.writeFile(path.join(OUT,'previews','formula_errors.ndjson'),errors.ndjson);
const xlsx=await SpreadsheetFile.exportXlsx(wb);
const destination=path.join(OUT,'复利时光_20260901起_数据档案.xlsx');
await xlsx.save(destination);
await fs.writeFile(path.join(OUT,'workbook_manifest.json'),JSON.stringify({file:destination,sheets:checks,source_notes:notes.length,source_images:images.length,observations:observations.length,body_facts:body.length,created:new Date().toISOString()},null,2));
console.log(JSON.stringify({output:destination,notes:notes.length,images:images.length,observations:observations.length,body_facts:body.length}));
