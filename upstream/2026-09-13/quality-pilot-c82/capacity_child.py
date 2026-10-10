#!/usr/bin/env python3
"""C82: preserve capacity measurements while treating memory as a guideline."""
import argparse
import hashlib
import json
import math
from pathlib import Path


GRID=(131072,196608,262144)
class C82Error(BaseException):
    pass

def run_all_rungs(original,*args,**kwargs):
    grid=tuple(kwargs.pop('grid',()))
    if grid!=GRID or kwargs.get('gate_gb')!=48:
        raise C82Error('expected frozen three-rung grid and descriptive 48GB guideline')
    records=[]
    for ctx in grid:
        # The original measurement procedure is unchanged. A singleton invocation
        # isolates its legacy memory-cutoff break; the outer loop always continues
        # after a successful measured response, irrespective of numeric peak.
        rows=original(*args,grid=(ctx,),**kwargs)
        if len(rows)!=1 or rows[0].get('ctx')!=ctx:
            raise C82Error('capacity procedure returned unexpected rows')
        if rows[0].get('error') or rows[0].get('error_kind'):
            raise C82Error('capacity infrastructure error; not a quality/memory verdict')
        peak=rows[0].get('server_peak_gb')
        if type(peak) not in (int,float) or not math.isfinite(peak) or peak<0:
            raise C82Error('invalid MLX peak telemetry; stop before next rung')
        records.extend(rows)
    return records

MIN_CPT=0.5
MAX_CPT=16.0


class CalibrationError(RuntimeError):
    pass


class CalibrationGuardDriver:
    def __init__(self,delegate,evidence_path,calibration_chars):
        self.delegate=delegate
        self.evidence_path=Path(evidence_path)
        self.calibration_chars=calibration_chars
        self.requests=0

    def preload(self,*args,**kwargs):
        raise CalibrationError('private child requires --no-preload; router is caller-owned')

    def complete(self,model,messages,params,timeout=3600,tools=None):
        if self.requests>=4:
            raise C82Error('approved capacity request count exceeded')
        first=self.requests==0
        if first:
            if params!={'max_tokens':1,'temperature':0.0} or timeout!=120 or tools is not None:
                raise CalibrationError('existing calibration request contract changed')
            if len(messages)!=1 or messages[0].get('role')!='user' or len(messages[0].get('content',''))!=self.calibration_chars:
                raise CalibrationError('existing calibration filler shape changed')
            if hashlib.sha256(messages[0]['content'].encode()).hexdigest()!='739c49f19cb5c7c403de43ad0effcd5ec3f2b76af72972aca97c199a4dfa2c72':
                raise CalibrationError('calibration filler differs from frozen baseline')
        self.requests+=1
        request={'model':model,'messages':messages,'params':params,'timeout':timeout,'tools':tools}
        request_path=self.evidence_path.parent/f'request-{self.requests:02d}.json'
        with request_path.open('x') as f:json.dump(request,f)
        try:response=self.delegate.complete(model,messages,params,timeout=timeout,tools=tools)
        except BaseException as exc:raise C82Error('capacity transport failed') from exc
        with (self.evidence_path.parent/f'response-{self.requests:02d}.json').open('x') as f:json.dump(response,f)
        if not first:
            expected=(130783,196115,261449)[self.requests-2]
            if response.get('prompt_tokens')!=expected:
                raise C82Error('capacity prompt occupancy differs from frozen baseline')
        if first:
            tokens=response.get('prompt_tokens')
            if type(tokens) is not int or tokens<=0:
                raise CalibrationError('calibration prompt_tokens must be a positive integer, not boolean')
            if tokens!=3210:raise CalibrationError('calibration occupancy differs from frozen baseline')
            cpt=self.calibration_chars/tokens
            if not MIN_CPT<=cpt<=MAX_CPT:
                raise CalibrationError('calibration chars/token outside registered 0.5..16 plausibility bounds')
            # This write and validation finish before calibrate_cpt can return to build_context.
            self.evidence_path.write_text(json.dumps({'validated':True,'prompt_tokens':tokens,
                'calibration_chars':self.calibration_chars,'chars_per_token':cpt,
                'minimum_cpt':MIN_CPT,'maximum_cpt':MAX_CPT,'request_count':1,
                'request_params':params,'timeout_s':timeout,
                'filler_sha256':hashlib.sha256(messages[0]['content'].encode()).hexdigest()},indent=2)+'\n')
        return response


def run(argv,evidence_path):
    from bench import run_capacity
    if '--no-preload' not in argv:
        raise CalibrationError('private child requires explicit --no-preload')
    original=run_capacity.MlxServeDriver
    def guarded_factory():
        return CalibrationGuardDriver(original(),evidence_path,len(run_capacity._CAL_FILLER*200))
    original_ladder=run_capacity.run_ladder
    run_capacity.run_ladder=lambda *a,**kw:run_all_rungs(original_ladder,*a,**kw)
    run_capacity.MlxServeDriver=guarded_factory
    try:
        return run_capacity.main(argv)
    finally:
        run_capacity.MlxServeDriver=original
        run_capacity.run_ladder=original_ladder


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calibration-evidence',required=True)
    args,remaining=parser.parse_known_args(argv)
    try:return run(remaining,Path(args.calibration_evidence))
    except CalibrationError as exc:
        print('CAPACITY CALIBRATION INSTRUMENT ERROR: '+str(exc),flush=True)
        return 2


if __name__=='__main__':raise SystemExit(main())
