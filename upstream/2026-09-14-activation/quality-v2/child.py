"""C84 canonical-generator guards; infrastructure failures escape Exception catch loops."""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import runpy
import sys
import time

TIMEOUT=21080


class PilotAbort(BaseException):
    pass


def emit(event,**fields):
    print('C84_EVENT '+json.dumps({'event':event,**fields},allow_nan=False),flush=True)


def save(path,value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def response_check(response):
    try:
        if not isinstance(response,dict) or response.get('error'):raise ValueError('server error/nonobject')
        choices=response['choices']
        if not isinstance(choices,list) or len(choices)!=1:raise ValueError('single choice required')
        choice=choices[0]
        if choice.get('index',0)!=0 or choice.get('finish_reason') not in ('stop','length','content_filter'):
            raise ValueError('missing/unknown finish reason or choice index')
        message=choice['message']
        if not isinstance(message,dict) or message.get('tool_calls'):raise ValueError('unexpected tool response')
        for key in ('content','reasoning','reasoning_content'):
            if message.get(key) is not None and not isinstance(message[key],str):raise ValueError('nonstring message field')
        a,b=message.get('reasoning'),message.get('reasoning_content')
        if a and b and a!=b:raise ValueError('conflicting reasoning aliases')
        usage=response['usage']
        for key in ('prompt_tokens','completion_tokens'):
            value=usage[key]
            if type(value) is not int or value<0 or (key=='prompt_tokens' and value==0):raise ValueError('invalid token usage')
        if 'total_tokens' in usage and (type(usage['total_tokens']) is not int or usage['total_tokens']!=usage['prompt_tokens']+usage['completion_tokens']):
            raise ValueError('invalid total usage')
        if choice['finish_reason']=='content_filter':return response
        timings=response['timings']
        for key in ('predicted_per_second','peak_memory'):
            value=timings.get(key)
            if type(value) not in (int,float) or not math.isfinite(value) or value<=0:raise ValueError('missing/invalid required telemetry: '+key)
        if timings.get('draft_kind')!='mtp':raise ValueError('MTP state missing/wrong')
        for key in ('draft_rounds','draft_n','draft_n_accepted'):
            value=timings[key]
            if type(value) is not int or value<0:raise ValueError('invalid MTP counter')
        if timings['draft_rounds']==0 or timings['draft_n']==0 or timings['draft_n_accepted']>timings['draft_n']:
            raise ValueError('MTP engagement missing or inconsistent')
        return response
    except (ValueError,KeyError,TypeError,AttributeError) as exc:
        raise PilotAbort('malformed completion protocol: '+str(exc)) from exc


class Guard:
    def __init__(self,expected,out,delegate,before,after):
        if len(expected)!=20 or len({(e['bench'],e['id']) for e in expected})!=20:
            raise PilotAbort('arm must contain exactly 20 unique approved identities')
        self.expected=expected;self.out=Path(out);self.delegate=delegate
        self.before=before;self.after=after;self.attempted=0;self.completed=0;self.pending=None;self.loads=0

    def post(self,path,payload,timeout=3600):
        if path=='/v1/models/load':
            if self.loads or self.attempted or payload!={'model':self.expected[0]['payload']['model'],'keep_alive':'240m'}:
                raise PilotAbort('unapproved/repeated load request')
            self.loads+=1
            try:return self.delegate(path,payload,timeout=timeout)
            except Exception as exc:raise PilotAbort('load transport failure: '+str(exc)) from exc
        if path!='/v1/chat/completions' or timeout!=TIMEOUT:raise PilotAbort('unapproved endpoint/timeout')
        if self.pending is not None or self.attempted>=20:raise PilotAbort('extra request or previous row missing')
        entry=self.expected[self.attempted]
        if json.dumps(payload)!=entry['wire']:raise PilotAbort('actual HTTP payload differs from approved bytes')
        self.before(self.attempted,entry)
        directory=self.out/f'request-{self.attempted+1:02d}';directory.mkdir(parents=True,exist_ok=False)
        (directory/'request.json').write_text(entry['wire'])
        self.attempted+=1
        save(self.out/'attempts.json',{'attempted':self.attempted,'maximum':20})
        started=time.monotonic()
        try:
            result=self.delegate(path,payload,timeout=timeout)
            # Preserve malformed responses too; strict validation below decides admission.
            (directory/'response.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
            response_check(result)
            if result['usage']['prompt_tokens']+102400>262144:
                raise PilotAbort('unexpected prompt headroom/budget clamping')
        except PilotAbort:raise
        except Exception as exc:
            save(directory/'error.json',{'error':str(exc),'graded':False,'retries':0})
            raise PilotAbort('completion transport failure: '+str(exc)) from exc
        self.pending={'entry':entry,'response':copy.deepcopy(result),'wall_s':time.monotonic()-started,'directory':directory}
        normalized=copy.deepcopy(result)
        message=normalized['choices'][0]['message']
        if not message.get('reasoning') and message.get('reasoning_content'):
            message['reasoning']=message['reasoning_content']
        return normalized

    def append(self,path,row,delegate):
        from bench import client,convergence,traces
        if self.pending is None:raise PilotAbort('unexpected/duplicate row')
        expected=self.pending['entry'];raw=self.pending['response'];usage=raw['usage'];choice=raw['choices'][0]
        want={'id':expected['id'],'bench':expected['bench'],'model':expected['payload']['model'],
              'sample':0,'sampler_seed':expected['seed'],'seed_base':0,'schema_version':2,
              'prompt_tokens':usage['prompt_tokens'],'completion_tokens':usage['completion_tokens'],
              'finish_reason':choice['finish_reason'],'thinking_budget':81920,
              'content':client.strip_thinking(choice['message'].get('content') or '')}
        if row.get('error') or row.get('error_kind') or row.get('recovery') or row.get('recovery_probe'):
            raise PilotAbort('canonical generation produced error/recovery row')
        if any(type(row.get(k)) is not type(v) or row.get(k)!=v for k,v in want.items()):
            raise PilotAbort('unexpected row identity/seed/tokens/content')
        for key in ('draft_kind','draft_rounds','draft_n','draft_n_accepted'):
            if row.get('draft',{}).get(key)!=(raw.get('timings') or {}).get(key):raise PilotAbort('row MTP counters differ')
        declared=convergence.is_converged(row)
        if row.get('converged') is not declared:raise PilotAbort('canonical convergence field is inconsistent')
        row['resolved_thinking_budget']=convergence.resolved_thinking_budget(row,context_limit=262144,max_tokens=102400)
        if row['resolved_thinking_budget'] is None:raise PilotAbort('resolved budget unavailable')
        row['converged']=convergence.is_converged(row)
        row['nonconv_kind']=traces.classify(row,trace_text=choice['message'].get('reasoning') or choice['message'].get('reasoning_content'))
        row['content_filter']=choice['finish_reason']=='content_filter'
        row['mtp_engagement']='unavailable-content-filter' if row['content_filter'] else 'reported-positive'
        row['content_sha256']=hashlib.sha256((choice['message'].get('content') or '').encode()).hexdigest()
        row['reasoning_sha256']=hashlib.sha256((choice['message'].get('reasoning') or choice['message'].get('reasoning_content') or '').encode()).hexdigest()
        delegate(path,row)
        save(self.pending['directory']/'row.json',row)
        self.completed+=1
        self.after(self.completed,row)
        self.pending=None

    def finish(self):
        if self.attempted!=20 or self.completed!=20 or self.pending is not None:raise PilotAbort('arm incomplete: expected exactly 20 requests and rows')


def run(phase,mode,pin,out):
 import screen as s
 from bench import benchmarks,client,generate
 f=s.frozen(pin,phase);a=f['arms'][mode]
 if Path(out).resolve()!=s.HERE/'runs'/phase/mode:raise PilotAbort('wrong private output')
 if client.BASE!='http://localhost:8000' or os.environ.get('MLX_SERVE_CONFIG')!=str(s.REGISTRY) or generate.results_root().resolve()!=s.HERE/'results'/phase:raise PilotAbort('client/registry/results mismatch')
 load,post,append=benchmarks.load,client._post,generate._append
 def selected(name,limit=None,seed=0):
  if name not in s.BENCHES or limit!=5 or seed!=0:raise PilotAbort('unapproved corpus/limit/seed')
  return copy.deepcopy(a['items'][name])
 def before(index,entry):
  emit('BEFORE_REQUEST',index=index,bench=entry['bench'],id=entry['id'])
  reply=sys.stdin.readline()
  if not reply or json.loads(reply)!={'ack':index}:raise PilotAbort('parent ACK absent/mismatched')
 g=Guard(a['requests'],out,post,before,lambda n,r:emit('ITEM',completed=n,row=r))
 def checked_append(path,row):
  if row.get('bench') not in a['results'] or Path(path).resolve()!=Path(a['results'][row['bench']]):raise PilotAbort('canonical output path differs')
  g.append(path,row,append)
 benchmarks.load=selected;client._post=g.post;generate._append=checked_append;argv=sys.argv
 try:
  sys.argv=[str(s.STACK/'benchmark/run.py'),*s.canonical_args(a)]
  runpy.run_path(str(s.STACK/'benchmark/run.py'),run_name='__main__');g.finish();emit('COMPLETE',attempted=g.attempted,completed=g.completed)
 finally:benchmarks.load=load;client._post=post;generate._append=append;sys.argv=argv

def main():
 p=argparse.ArgumentParser();p.add_argument('--phase',choices=['after'],required=True);p.add_argument('--mode',choices=['native16','tq4'],required=True);p.add_argument('--frozen-sha',required=True);p.add_argument('--out',required=True);a=p.parse_args()
 try:run(a.phase,a.mode,a.frozen_sha,a.out);return 0
 except BaseException as exc:emit('ERROR',error=str(exc),graded=False);return 2
if __name__=='__main__':raise SystemExit(main())
