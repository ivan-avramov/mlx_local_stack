import os, pathlib, json, subprocess
repo=pathlib.Path(os.environ['STACK_REPO']);q=pathlib.Path(os.environ['STACK_WORKDIR'])/'queue';py=str(repo/'.venv-bench/bin/python');model='Ornith-1.0-35B-mlx-uniform-4bit'
env=dict(os.environ,MLX_SERVE_CONFIG=str(q/'bench_overlay_q4_exp.yaml'))
r=subprocess.run([py,str(repo/'benchmark/run.py'),'grade','--models',model,'--benches','mbppplus','--tune','m34afexp'],cwd=repo,env=env)
score=json.loads((repo/'benchmark/results'/model/'mbppplus.m34afexp.score.json').read_text())
assert r.returncode==0 and score.get('acc') is not None and not score.get('errors'),score.get('note')
subprocess.run([py,str(q/'paired_ofat.py'),'--bench','mbppplus','--a',model,'m34afexp','--b',model,'m34afnat','--json',str(q/'paired_M34a_full_mbppplus.json')],cwd=repo/'benchmark',env=dict(env,PYTHONPATH='.'),check=True)
print('REGRADE AND PAIRED DONE',flush=True)
