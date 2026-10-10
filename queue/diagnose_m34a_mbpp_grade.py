import os,sys,pathlib,subprocess,runpy,time
repo=pathlib.Path(os.environ['STACK_REPO']);q=pathlib.Path(os.environ['STACK_WORKDIR'])/'queue'
sys.path.insert(0,str(repo/'benchmark'))
from bench import grade
original=grade.grade_evalplus
raw_run=subprocess.run
def diagnostic_runner(cmd,**kw):
    if cmd[:2]==['docker','run']:
        pos=cmd.index(grade.EVALPLUS_IMAGE)
        cmd=cmd[:pos]+['-e','PYTHONUNBUFFERED=1']+cmd[pos:]
        kw.pop('capture_output',None)
        with (q/'mbpp_evalplus_diagnostic.log').open('a',buffering=1) as f:
            f.write('START '+time.strftime('%Y-%m-%d %H:%M:%S')+'\n')
            return raw_run(cmd,stdout=f,stderr=subprocess.STDOUT,**kw)
    return raw_run(cmd,**kw)
def wrapped(*a,**kw):
    kw['runner']=diagnostic_runner
    return original(*a,**kw)
grade.grade_evalplus=wrapped
sys.argv=[str(repo/'benchmark/run.py'),'grade','--models','Ornith-1.0-35B-mlx-uniform-4bit','--benches','mbppplus','--tune','m34afexp']
runpy.run_path(str(repo/'benchmark/run.py'),run_name='__main__')
