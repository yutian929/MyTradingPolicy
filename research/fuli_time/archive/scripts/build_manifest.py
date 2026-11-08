"""Rebuild the explicit browser-observed download manifest; no network access."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
DATA='''09-29|6abb5809000000001402ee0d|今天有事更新晚了|1040g3k0325mkn|7
09-28|6ab9f4e10000000001009dda|指标更新|1040g3k8325l9bo|7
09-24|6ab4b1c40000000015004e3a|指标更新|1040g3k0325g4t|7
09-23|6ab359830000000014030989|指标更新|1040g3k0325eqt|7
09-22|6ab2040c000000003a022967|指标更新|1040g3k8325dh78|7
09-21|6ab0bcb30000000038001a11|指标更新|1040g3k0325c98|7
09-18|6aacccd2000000002603ae6e|指标更新|1040g3k03258e7|7
09-17|6aab736d0000000026008ffb|指标更新|1040g3k8325742k|7
09-16|6aaa345c000000002a02ff89|指标更新|1040g3k83255t40|7
09-15|6aa8cd60000000002a026e0d|指标更新|1040g3k83254h9m|7
09-14|6aa77dc8000000000b0013cd|观点分享|1040g3k832538b1|7
09-11|6aa38ecc0000000026030f01|数据更新|1040g3k8324vdda|7
09-10|6aa235f90000000028033e35|比想象中强，但不追|1040g3k0324u3a|7
09-09|6aa0e6be0000000027015c1e|数据更新|1040g3k8324sqcn|7
09-08|6a9f94d1000000002901abb7|别因为今天涨了就冲动|1040g3k8324rh50|7
09-07|6a9e3f31000000000b034dd6|不到A，不考虑进|1040g3k0324q7e|7
09-04|6a9a526400000000270166cc|数据和昨天比，没有变化|1040g3k8324mcpg|7
09-03|6a98f8cb000000002b026c26|今日数据更新|1040g3k0324l2j|7
09-02|6a97b6d7000000002a0257db|阅读破100万，做红利低波的这段日子|1040g3k8324jr9t|1
09-02|6a97acdb000000000b00cd1b|今日数据更新|1040g3k8324jq2s|7
09-01|6a965705000000002b000cb5|评分D级！|1040g3k8324igbi|7
11-06|6aed5df300000000090021da|指标更新|1040g3k83277fuf|7
11-05|6aec0a85000000000f026f69|指标更新|1040g3k832766gq|7
11-04|6aeab9890000000016030b75|指标更新|1040g3k83274tc|7
11-03|6ae96d210000000010011cb4|指标更新|1040g3k03273k9b|7
11-02|6ae8167d000000001001375f|指标更新|1040g3k03272av|7
10-30|6ae4218e0000000019002879|指标更新|1040g3k8326ufa,1040g3k0326ufao|7
10-29|6ae2d1b40000000033011c1f|指标更新|1040g3k0326t6a|7
10-28|6ae188820000000036011e51|指标更新|1040g3k0326ru5,1040g3k0326ru4v|7
10-27|6ae02c26000000000e02d271|指标更新|1040g3k8326qjk|7
10-26|6adeda5c0000000002008e05|持有观望|1040g3k8326pacj|7
10-21|6ad83e820000000033020718|很多朋友问我什么时候恢复更新||0
10-20|6ad6f0ad000000002a00d12b|暂时停更|1040g008326hj38|1
10-19|6ad5a8d40000000026014cc0|风险信号集中|1040g3k8326gb2o|6
10-16|6ad1abea000000001b01d2c3|评分D级|1040g3k0326cef|7
10-15|6ad0586f000000001c01cb10|谨慎mai入|1040g3k0326b51|7
10-14|6acf1137000000001a0328af|E级评分|1040g3k03269t2|7
10-13|6acdb6980000000002012f64|指标更新|1040g3k83268ioj,1040g3k03268ioj|7
10-12|6acc655d000000001a025d10|E级评分亮红灯！|1040g3k832679ht|7
10-09|6ac879560000000018019c2f|评分D|1040g3k03263f1|7
10-08|6ac71edd0000000018017fcc|又到了边涨边卖的区间|1040g2sg32624nc|7
09-30|6abc981f000000001b01e11d|指标更新|1040g3k0325nrp|7'''
rows=[]
for row in DATA.splitlines():
    d,id,title,prefixes,count=row.split('|')
    unique={}
    for prefix in filter(None,prefixes.split(',')):
        for p in sorted(Path('/home/yutian/下载').glob(prefix+'*.webp')):
            unique.setdefault(hashlib.sha256(p.read_bytes()).hexdigest(),str(p))
    assert len(unique)==int(count),(d,len(unique),count)
    kind='daily' if int(count)>1 else 'notice'
    if id not in ['6a97b6d7000000002a0257db','6ad83e820000000033020718']:
        month,day=map(int,d.split('-')); title=f'2026.{month}.{day}红利低波，'+title
    rows.append(dict(note_id=id,date='2026-'+d,title=title,note_type=kind,url='https://www.xiaohongshu.com/explore/'+id,expected_images=int(count),files=list(unique.values()),captured_on='2026-11-08'))
rows.sort(key=lambda r:(r['date'],r['note_id']))
dest=ROOT/'research/fuli_time/archive/source_manifest.json'
dest.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
print({'notes':len(rows),'images':sum(len(r['files']) for r in rows),'daily':sum(r['note_type']=='daily' for r in rows)})
