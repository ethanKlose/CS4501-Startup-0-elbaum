"""Run deterministic or paid live evaluation with explicit engine attribution."""
import argparse
import json
import os
from pathlib import Path
import time
from app.services.llm import FakeLLM, AnthropicLLM
from app.services.planner import run_with_retries,PlanFailed
from app.services.types import PlanContext,DayCtx
from app.config import settings

SCENARIOS=[
    ('baseline',{}),('vegan',{'restrictions':['vegan']}),('nut_allergy',{'restrictions':['nut_allergy']}),
    ('no_wednesday_cooking',{'days':[DayCtx(i,0 if i==2 else 60) for i in range(7)]}),
    ('high_protein',{'goal':'high_protein'}),('microwave_only',{'equipment':['microwave','fridge'],'allow_freezer':False}),
]


def evaluate(live=False,repeats=1):
    if live and not settings.anthropic_api_key.strip():
        return {'status':'unavailable','engine':'anthropic','reason':'ANTHROPIC_API_KEY is not configured','results':[]}
    results=[]
    for name,overrides in SCENARIOS:
        for repeat in range(repeats):
            llm=AnthropicLLM(settings.anthropic_api_key,settings.anthropic_model) if live else FakeLLM()
            context=PlanContext(budget=150,days=[DayCtx(i,45) for i in range(7)],seed=repeat+1,**{k:v for k,v in overrides.items() if k!='days'})
            if 'days' in overrides:context.days=overrides['days']
            start=time.perf_counter()
            try:
                plan,attempts,warnings=run_with_retries(llm,context)
                result=dict(success=True,attempts=attempts,warnings=warnings,meals=len(plan['meals']))
            except PlanFailed as e:result=dict(success=False,attempts=len(context.generation_trace),errors=e.errors)
            metrics=getattr(llm,'metrics',[])
            tokens_known=bool(metrics) and all(m['input_tokens'] is not None and m['output_tokens'] is not None for m in metrics)
            input_tokens=sum(m['input_tokens'] for m in metrics) if tokens_known else None
            output_tokens=sum(m['output_tokens'] for m in metrics) if tokens_known else None
            cost=None
            if tokens_known and os.environ.get('INPUT_USD_PER_MILLION') and os.environ.get('OUTPUT_USD_PER_MILLION'):
                cost=(input_tokens*float(os.environ['INPUT_USD_PER_MILLION'])+output_tokens*float(os.environ['OUTPUT_USD_PER_MILLION']))/1e6
            results.append(dict(scenario=name,repeat=repeat,latency_seconds=round(time.perf_counter()-start,3),input_tokens=input_tokens,output_tokens=output_tokens,estimated_usd=cost,**result))
    return {'status':'completed','engine':'anthropic' if live else 'fake','model':settings.anthropic_model if live else None,'results':results,'success_rate':sum(r['success'] for r in results)/len(results)}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');parser.add_argument('--repeats',type=int,default=1);parser.add_argument('--output',default='evals/latest.json')
    args=parser.parse_args()
    if not 1<=args.repeats<=10:parser.error('repeats must be 1..10')
    report=evaluate(args.live,args.repeats)
    Path(args.output).parent.mkdir(parents=True,exist_ok=True);Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'engine':report['engine'],'output':args.output}))
    raise SystemExit(2 if report['status']=='unavailable' else 0 if all(r['success'] for r in report['results']) else 1)
