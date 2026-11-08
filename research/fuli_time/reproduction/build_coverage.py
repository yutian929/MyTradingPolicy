"""Build the original-field and additional-indicator evidence matrix after validation."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/fuli_time_reproduction'
snapshot=json.loads((OUT/'20261106_113000/snapshot.json').read_text())
summary=pd.read_csv(OUT/'technical_summary.csv')
technical=summary.query("mode=='independent_1130' and split=='holdout'").set_index('metric').to_dict('index')
v=json.loads((ROOT/'research/fuli_time/reproduction/valuation_validation.json').read_text())
valuation={r['metric']:r for r in v['source_comparisons'] if r['split']=='holdout'}
score=snapshot['score_model']['validation'];rows=[]
for key,m in snapshot['metrics'].items():
    row=dict(metric=key,label=m['label'],implementation_status=m['status'],sample_value=m['value'],
             input_or_formula_gap=m['reason'],independent_holdout_n=None,holdout_mae=None,holdout_max_error=None,
             tolerance=m.get('tolerance'),acceptance='not_independently_established')
    if key in technical:
        t=technical[key];row.update(independent_holdout_n=t['n'],holdout_mae=t['mae'],holdout_max_error=t['max_abs_error'],
                                    tolerance=t['absolute_tolerance'],acceptance='passed_recent_holdout')
    elif key in ['dividend_yield_pct','bond_yield_10y_pct','equity_bond_spread_pp']:
        t=valuation[key];row.update(independent_holdout_n=t['n'],holdout_mae=t['mae'],holdout_max_error=t['max_abs_error'],acceptance='recent_source_match_not_all_history')
    elif key=='score_precise':
        row.update(independent_holdout_n=score['holdout_rows'],holdout_mae=score['holdout_mae_points'],
                   holdout_max_error=score['holdout_max_error_points'],acceptance='approximation_exceeds_3_point_target_on_one_day')
    elif key.startswith('forward_') or key=='same_score_samples':row['acceptance']='independent_statistics_not_original_cohort'
    elif key.startswith('macd_'):row['acceptance']='additional_indicator_no_author_reference'
    elif m['value'] is None:row['acceptance']='unavailable_or_action_abstained'
    rows.append(row)
pd.DataFrame(rows).to_csv(OUT/'function_matrix.csv',index=False,encoding='utf-8-sig')
print(f'{len(rows)} fields; {len(technical)} independently validated technical fields')
