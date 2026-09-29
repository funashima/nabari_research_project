#!/usr/bin/env python3
"""Validate study JSON files and estimate paired participant-level differences.

Python standard library only. Practice files require --practice; no mock results
are created. Incomplete participants are listed but excluded from paired effects.
"""
import argparse
import hashlib
import json
import math
import random
import re
import statistics as st
from pathlib import Path

PLANS=[('enhanced','X','baseline','Y'),('baseline','X','enhanced','Y'),('enhanced','Y','baseline','X'),('baseline','Y','enhanced','X')]
FIELDS=('success_rate','effective_seconds','action_count')
def valid_number(x): return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def expected_tasks(pid):
    p=PLANS[(int(pid[1:])-1)%4]
    return [(f'{p[s+1]}{i}',p[s],s//2+1,p[s+1]) for s in (0,2) for i in (1,2,3)]
def validate(d,expected_kind='observed'):
    if not isinstance(d,dict) or d.get('schemaVersion')!=1: raise ValueError('Unsupported export schema')
    if d.get('dataKind')!=expected_kind:raise ValueError(f'dataKind must be {expected_kind}; never mix practice and observed')
    pid=d.get('participant','')
    if not re.fullmatch(r'P\d{3}',pid) or pid=='P000':raise ValueError('Invalid participant ID')
    if d.get('group')!=(int(pid[1:])-1)%4+1:raise ValueError('Group does not match participant schedule')
    if d.get('limitSeconds')!=180:raise ValueError('Protocol limit must be 180 seconds')
    if not re.fullmatch(r'[a-f0-9]{64}',d.get('datasetSha256','')):raise ValueError('Dataset SHA-256 is required')
    rows=d.get('records')
    if not isinstance(rows,list) or len(rows)>6:raise ValueError('Invalid record list')
    if d.get('complete') is not (len(rows)==6):raise ValueError('Complete flag disagrees with task count')
    for i,r in enumerate(rows):
        if not isinstance(r,dict):raise ValueError('Each record must be an object')
        if (r.get('taskId'),r.get('condition'),r.get('period'),r.get('set'))!=expected_tasks(pid)[i]:raise ValueError('Missing, duplicate or out-of-order task / condition')
        t=r.get('elapsedSeconds');out=r.get('outcome')
        if not valid_number(t) or not 0<=t<=180:raise ValueError('Invalid elapsed time')
        if out not in ('success','failure','timeout','assisted'):raise ValueError('Invalid outcome')
        if out=='timeout' and t<179.5:raise ValueError('Timeout recorded before time limit')
        expected=t if out=='success' else 180
        if not valid_number(r.get('effectiveSeconds')) or abs(r['effectiveSeconds']-expected)>.002:raise ValueError('Effective time does not match outcome')
        if not isinstance(r.get('actions'),list):raise ValueError('Actions must be an array')
        prev=-1
        for a in r['actions']:
            if not isinstance(a,dict) or a.get('action') not in ('category','search','detail','source','reset'):raise ValueError('Unknown action')
            at=a.get('atSeconds')
            if not valid_number(at) or not prev<=at<=t+.01:raise ValueError('Invalid action timestamp')
            prev=at
    return d

def quantile(xs,p):
    xs=sorted(xs);i=(len(xs)-1)*p;lo=math.floor(i);hi=math.ceil(i)
    return xs[lo]+(xs[hi]-xs[lo])*(i-lo)
def paired_effect(values,seed=20260929,replicates=5000):
    estimate=st.mean(values)
    if len(values)<2:return {'mean_difference':estimate,'ci95':None,'n':len(values)}
    rng=random.Random(seed);bs=[st.mean(rng.choices(values,k=len(values))) for _ in range(replicates)]
    return {'mean_difference':estimate,'ci95':[quantile(bs,.025),quantile(bs,.975)],'n':len(values)}

def summarize(documents):
    if not documents:return {'status':'no_data','participants':0,'effects':None,'claim':'利用者実験は未実施。効果は推定できない。'}
    if len({d['participant'] for d in documents})!=len(documents):raise ValueError('Duplicate participant export; choose one final file per participant')
    if len({(d['datasetSha256'],d.get('datasetAsOf'),d['limitSeconds'],d['dataKind']) for d in documents})!=1:raise ValueError('Dataset / protocol mismatch across participants')
    complete=[d for d in documents if d['complete']]
    excluded=[d['participant'] for d in documents if not d['complete']]
    paired=[]
    for d in complete:
        item={'participant':d['participant'],'group':d['group']}
        for condition in ('enhanced','baseline'):
            rows=[r for r in d['records'] if r['condition']==condition]
            successes=[r for r in rows if r['outcome']=='success']
            item[condition]={'success_rate':len(successes)/3,'effective_seconds':st.mean(r['elapsedSeconds'] if r['outcome']=='success' else 180 for r in rows),'successful_seconds':st.mean(r['elapsedSeconds'] for r in successes) if successes else None,'action_count':st.mean(len(r['actions']) for r in rows)}
        paired.append(item)
    effects={k:paired_effect([p['enhanced'][k]-p['baseline'][k] for p in paired]) for k in FIELDS} if paired else None
    return {'status':'descriptive_pilot','dataKind':documents[0]['dataKind'],'participants':len(documents),'complete_participants':len(complete),'excluded_incomplete':excluded,'datasetSha256':documents[0]['datasetSha256'],'group_counts':{str(g):sum(d['group']==g for d in complete) for g in range(1,5)},'difference_direction':'enhanced minus baseline','effects':effects,'participant_summaries':paired,'limitations':['探索的な便宜標本。地域住民全体への一般化はできない。','課題セットの難易度差・順序効果を確認すること。','区間は参加者単位の百分位ブートストラップ。少数例では不安定。','成功時だけの時間は参考値。失敗・支援・時間切れは主要時間指標では180秒。','actionsは検索・カテゴリ・詳細・出典・リセットの記録数。全クリック数ではない。']}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('files',nargs='*',type=Path);p.add_argument('--out',type=Path,default=Path('results/study_summary.json'));p.add_argument('--practice',action='store_true');p.add_argument('--dataset',type=Path,help='Require exports to match this exact dataset file')
    a=p.parse_args();kind='practice' if a.practice else 'observed'
    try:
        docs=[validate(json.loads(f.read_text(encoding='utf-8')),kind) for f in a.files]
        if a.dataset:
            digest=hashlib.sha256(a.dataset.read_bytes()).hexdigest()
            if any(d['datasetSha256']!=digest for d in docs):raise ValueError('Export is from a different dataset version')
        result=summarize(docs)
    except (OSError,ValueError,TypeError,KeyError) as e:p.error(str(e))
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('participant_summaries',)},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
