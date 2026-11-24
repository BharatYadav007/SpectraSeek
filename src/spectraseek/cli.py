"""CLI for reproducible experiments and operator-controlled authorized surveys."""
import argparse
import json
from pathlib import Path
import re
import sys
import pandas as pd
from .dataset import simulate
from .experiment import evaluate, recommend


def main(argv=None):
    p=argparse.ArgumentParser(prog='spectraseek'); sub=p.add_subparsers(dest='command',required=True)
    demo=sub.add_parser('demo'); demo.add_argument('--output',default='data/synthetic.csv'); demo.add_argument('--seed',type=int,default=42); demo.add_argument('--sessions',type=int,default=40)
    exp=sub.add_parser('evaluate'); exp.add_argument('dataset'); exp.add_argument('--budget',type=int,default=3); exp.add_argument('--output',default='results/evaluation.json')
    rec=sub.add_parser('recommend'); rec.add_argument('dataset'); rec.add_argument('--visited',nargs='*',default=[]); rec.add_argument('--found',nargs='*',default=[]); rec.add_argument('--strategy',choices=['logistic','random_forest','empirical_greedy'],default='random_forest')
    sub.add_parser('interfaces'); sub.add_parser('init-db')
    export=sub.add_parser('export'); export.add_argument('--output',default='data/measured.csv')
    scan=sub.add_parser('scan'); scan.add_argument('--session',required=True); scan.add_argument('--site',required=True); scan.add_argument('--config',required=True); scan.add_argument('--interface'); scan.add_argument('--authorized',action='store_true',required=True)
    a=p.parse_args(argv)
    try:
        if a.command=='demo':
            data=simulate(a.seed,a.sessions); path=Path(a.output); path.parent.mkdir(parents=True,exist_ok=True); data.to_csv(path,index=False); print(f'Wrote {len(data)} SYNTHETIC records to {path}')
        elif a.command=='evaluate':
            result=evaluate(pd.read_csv(a.dataset,dtype={'session':str}),a.budget); path=Path(a.output); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8'); print(json.dumps({'source':result['source'],'models':result['models'],'strategies':result['strategies']},indent=2)); print(f'Saved {path}')
        elif a.command=='recommend':
            print(json.dumps(recommend(pd.read_csv(a.dataset,dtype={'session':str}),a.visited,a.found,a.strategy),indent=2))
        elif a.command=='interfaces':
            from .collector import interfaces
            print('\n'.join(interfaces()))
        else:
            from .storage import SurveyRepository
            if a.command=='scan':
                from .collector import scan as collect
                cfg=json.loads(Path(a.config).read_text(encoding='utf-8')); site=cfg['sites'][a.site]; targets={k.lower():v for k,v in cfg['targets'].items()}
                if not targets or len(targets)!=len(cfg['targets']) or any(not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',k) for k in targets) or any(not isinstance(v,str) or not v.strip() for v in targets.values()) or len(set(targets.values()))!=len(targets):
                    raise ValueError('Use unique target labels and valid authorized BSSIDs')
                repo=SurveyRepository(); snapshot=collect(a.interface); repo.record(a.session,a.site,float(site['x']),float(site['y']),targets,snapshot,int(cfg.get('min_quality',0))); print('Recorded authorized target outcomes')
            elif a.command=='init-db':
                SurveyRepository().initialize(); print('Database schema ready')
            elif a.command=='export':
                data=SurveyRepository().export(); path=Path(a.output); path.parent.mkdir(parents=True,exist_ok=True); data.to_csv(path,index=False); print(f'Exported {len(data)} measured rows')
        return 0
    except Exception as exc:
        print(f'Error: {exc}',file=sys.stderr); return 1
