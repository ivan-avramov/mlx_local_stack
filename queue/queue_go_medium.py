import hashlib, json, math, os, random, re, shutil, signal, statistics, subprocess, sys, threading, time
from pathlib import Path
WD=os.environ['STACK_WORKDIR']; REPO=os.environ['STACK_REPO']; PY=f"{REPO}/.venv-bench/bin/python"
OUT=f"{WD}/queue"; OFF_OVERLAY=f"{OUT}/bench_overlay_q4.yaml"
LOG=open(f"{OUT}/go_medium.log",'a',buffering=1)
def log(m):
    LOG.write(f"[{time.strftime('%m-%d %H:%M:%S')}] {m}\n")

def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)

def listeners():
    return [int(x) for x in sh(['lsof', '-nP', '-iTCP:8000', '-sTCP:LISTEN', '-t']).stdout.split()]

class StageFail(Exception):
    pass

def fail(m):
    log(f'FATAL: {m}')
    raise StageFail(m)

def stop_router():
    for p in listeners():
        try:
            os.kill(p, signal.SIGTERM)
        except OSError:
            pass
    for _ in range(30):
        if not listeners():
            break
        time.sleep(1)
    for p in listeners():
        try:
            os.kill(p, signal.SIGKILL)
        except OSError:
            pass
    time.sleep(2)
    if listeners():
        fail(':8000 still busy')
    for _ in range(60):
        if not sh(['pgrep', '-f', 'mlx_vlm.server|mlx_vlm/server']).stdout.split():
            break
        time.sleep(2)
    log('router stopped; 0 listeners; worker gone')

def start_router(overlay):
    env = dict(os.environ)
    env.pop('APC_ENABLED', None)
    env['MLX_VLM_CACHE_SESSION_MAX'] = '2'
    env['MLX_SERVE_CONFIG'] = overlay
    subprocess.Popen(['uv', 'run', 'mlx-serve', 'start'], cwd=REPO, env=env, stdout=open(f'{REPO}/logs/main_model.log', 'a'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(90):
        if listeners():
            break
        time.sleep(2)
    if not listeners():
        fail('router did not come up')
    pid = listeners()[0]
    e = sh(['ps', '-Eww', '-o', 'command=', '-p', str(pid)]).stdout
    ok = 'MLX_SERVE_CONFIG=' + overlay in e and 'APC_ENABLED' not in e and ('MLX_VLM_CACHE_SESSION_MAX=2' in e)
    log(f'router up pid={pid} overlay={os.path.basename(overlay)} env_ok={ok}')
    if not ok:
        fail('router env wrong')

def ensure_router(overlay):
    if listeners():
        e = sh(['ps', '-Eww', '-o', 'command=', '-p', str(listeners()[0])]).stdout
        if 'MLX_SERVE_CONFIG=' + overlay in e and 'APC_ENABLED' not in e and ('MLX_VLM_CACHE_SESSION_MAX=2' in e):
            log(f'router already on {os.path.basename(overlay)}')
            return
        stop_router()
    start_router(overlay)

def unload():
    import urllib.request
    if not sh(['pgrep', '-f', 'mlx_vlm.server']).stdout.strip():
        return
    try:
        urllib.request.urlopen(urllib.request.Request('http://localhost:8000/v1/models/unload', method='POST', data=b''), timeout=120).read()
    except Exception as ex:
        log(f'unload POST: {ex}')
    for _ in range(24):
        if not sh(['pgrep', '-f', 'mlx_vlm.server']).stdout.strip():
            log('worker unloaded (pgrep verified)')
            return
        time.sleep(5)
    fail('worker still alive after unload')

def worker_cmdline():
    pids = sh(['pgrep', '-f', 'mlx_vlm.server']).stdout.split()
    return sh(['ps', '-o', 'command=', '-p', pids[0]]).stdout if pids else ''

def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()

def make_overlay(name, edits):
    """Copy the draft-OFF overlay and insert extra registry lines right after `    hf_path:` of the named entry."""
    src = open(OFF_OVERLAY).read().splitlines()
    out = []
    hit = False
    inside = False
    for line in src:
        out.append(line)
        if re.match('^\\s*- name: ' + re.escape(name) + '\\s*$', line):
            inside = True
            continue
        if inside and re.match('^\\s*hf_path:', line):
            for e in edits:
                out.append(re.match(r'^\s*', line).group() + e)
            inside = False
            hit = True
    if not hit:
        fail(f'overlay edit: entry {name} not found')
    p = f"{OUT}/overlay_q4_{name}_{hashlib.sha1(''.join(edits).encode()).hexdigest()[:6]}.yaml"
    open(p, 'w').write('# QUEUE OVERLAY — generated from the q3 draft-OFF overlay + ' + ' | '.join(edits) + ' on ' + name + '\n' + '\n'.join(out) + '\n')
    import yaml
    yaml.safe_load(open(p))
    return p

def rows(model, bench, tune):
    p = f'{REPO}/benchmark/results/{model}/{bench}.{tune}.jsonl'
    return [json.loads(l) for l in open(p)] if os.path.isfile(p) else []

def run_generate(model, bench, tune, limit, tag, overlay, expect_draft='off', extra=None, samples=1, bound_h=20):
    env = dict(os.environ)
    env.pop('APC_ENABLED', None)
    env['MLX_SERVE_CONFIG'] = overlay
    cmd = [PY, f'{REPO}/benchmark/run.py', 'generate', '--models', model, '--benches', bench, '--limit', f'{bench}={limit}', '--seed', '0', '--order', 'model', '--sampling-profile', 'deployed', '--tune', tune, '--chunks', 'all', '--probe-timeout', '7800', '--samples', str(samples)] + list(extra or [])
    log(f"RUN {tag}: {' '.join(cmd)}")
    s = sha(overlay)
    log(f'overlay {os.path.basename(overlay)} sha256={s}')
    d = subprocess.Popen(cmd, cwd=REPO, env=env, stdout=open(f'{OUT}/{tag}.log', 'a'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    open(f'{OUT}/{tag}.pid', 'w').write(str(d.pid))
    t0 = time.time()
    wenv = dict(env)
    wenv['PYTHONPATH'] = f'{REPO}/benchmark'
    w = subprocess.Popen([PY, f'{REPO}/benchmark/m1/bench_watch.py', '--models', model, '--bench', bench, '--tune', tune, '--total', str(limit * samples), '--driver-pattern', 'run.py generate', '--out', f'{OUT}/watch_{tag}.json', '--interval', '300'], cwd=REPO, env=wenv, stdout=open(f'{OUT}/watch_{tag}.log', 'a'), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    man = f'{REPO}/benchmark/results/{model}/{bench}.{tune}.manifest.json'
    checked = False
    rc = None
    cmd_checked = False
    while rc is None:
        rc = d.poll()
        if not checked and os.path.isfile(man) and (os.path.getmtime(man) >= t0 - 5):
            try:
                mf = json.load(open(man))
                dk = (mf.get('runtime') or {}).get('draft_kind')
                rs = (mf.get('registry') or {}).get('sha256')
                me = (mf.get('kv') or {}).get('moe_expand')
                ok = dk == expect_draft and rs == s
                log(f"C35 check {model} {tag}: runtime.draft_kind={dk} (expect {expect_draft}) registry.sha256_match={rs == s} kv.moe_expand={me} -> {('OK' if ok else 'MISMATCH')}")
                checked = True
                if not ok:
                    d.kill()
                    w.kill()
                    fail('provenance mismatch — driver killed; rows are FALSE-PROVENANCE')
            except StageFail:
                raise
            except Exception:
                pass
        if not cmd_checked:
            c = worker_cmdline()
            if c:
                log(f"worker cmdline: draft={'--draft-kind' in c} moe={'--moe-expand' in c} :: {c[-160:]}")
                cmd_checked = True
                if (expect_draft == 'off') == ('--draft-kind' in c):
                    d.kill()
                    w.kill()
                    fail(f'worker draft state contradicts expect_draft={expect_draft}')
        if time.time() - t0 > bound_h * 3600:
            d.kill()
            log(f'TIMEOUT {tag} after {bound_h} h')
            rc = -9
            break
        time.sleep(15)
    w.kill()
    log(f'END {tag} rc={rc}')
    return rc

def summarize(model, bench, tune, expect, tag):
    rs = rows(model, bench, tune)
    if not rs:
        log(f'SUMMARY {tag}: NO ROWS')
        return {'n': 0, 'errors': ['no rows']}
    w = [r['wall_s'] for r in rs if r.get('wall_s') is not None]
    ct = [r.get('completion_tokens') or 0 for r in rs]
    s = {'n': len(rs), 'expect': expect, 'errors': [(r['id'], str(r.get('error'))[:60]) for r in rs if r.get('error')], 'converged': sum((1 for r in rs if r.get('converged'))), 'nonconv_kinds': dict(((k, sum((1 for r in rs if r.get('nonconv_kind') == k))) for k in {r.get('nonconv_kind') for r in rs if r.get('nonconv_kind')})), 'wall_mean_s': round(statistics.mean(w), 1) if w else None, 'wall_max_s': round(max(w), 1) if w else None, 'wall_sum_h': round(sum(w) / 3600, 2) if w else None, 'tok_mean': round(statistics.mean(ct)) if ct else None, 'tok_max': max(ct) if ct else None, 'draft_engaged': sum((1 for r in rs if (r.get('draft') or {}).get('draft_n'))), 'acc_rate': (lambda a: round(statistics.mean(a), 3) if a else None)([r['draft']['draft_n_accepted'] / r['draft']['draft_n'] for r in rs if (r.get('draft') or {}).get('draft_n')])}
    log(f'SUMMARY {tag}: {json.dumps(s)}')
    return s

def grade(model, bench, tune, tag):
    g = sh([PY, f'{REPO}/benchmark/run.py', 'grade', '--models', model, '--benches', bench, '--tune', tune], cwd=REPO, env={**os.environ, 'MLX_SERVE_CONFIG': OFF_OVERLAY})
    open(f'{OUT}/grade_{tag}.log', 'a').write(g.stdout + g.stderr)
    log(f'END grade {tag} rc={g.returncode}')
    try:
        s = json.load(open(f'{REPO}/benchmark/results/{model}/{bench}.{tune}.score.json'))
        log(f"SCORE {tag}: acc={s.get('acc')} acc_strict={s.get('acc_strict')} n={s.get('n')} conv={s.get('conv_rate')} errors={s.get('errors')} note={s.get('note')}")
        if s.get('acc') is None:
            log(f'WARN: acc None for {tag} (docker?)')
    except Exception as ex:
        log(f'WARN: no score for {tag}: {ex}')



OVERLAY=OUT+'/bench_overlay_q7_go_medium.yaml'
MODELS=['Qwen3.8-27B-mlx-uniform-4bit','Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed']
ITEMS='counter,dnd-character,forth,alphametics,crypto-square,beer-song,book-store,bottle-song,bowling,connect,dominoes,error-handling,food-chain,hexadecimal,kindergarten-garden,ledger,markdown,matrix,octal,paasio,palindrome-products,pig-latin'.split(',')
PILOT=sorted(random.Random(0).sample(ITEMS,5));REST=[i for i in ITEMS if i not in PILOT]
def env_oc():
    e=dict(os.environ);e.pop('APC_ENABLED',None);e.update(MLX_SERVE_CONFIG=OVERLAY,TMPDIR=WD+'/scratch/octmp',PATH=WD+'/o39/opencode-1.18.15:'+e['PATH']);return e
def read_rows(p):return [json.loads(l) for l in Path(p).read_text().splitlines()] if Path(p).exists() else []
def leg(model,items,out,tag):
    cmd=[PY,REPO+'/benchmark/run_opencode_probe.py','--model',model,'--items',','.join(items),'--lang','go','--out',out]
    d=subprocess.Popen(cmd,cwd=REPO,env=env_oc(),stdout=open(OUT+'/'+tag+'.log','a'),stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
    Path(OUT+'/'+tag+'.pid').write_text(str(d.pid));log('RUN '+tag+' pid='+str(d.pid));start=time.time();last=start;previous=len(read_rows(out));checked=False;worker_checked=False
    while d.poll() is None:
        mp=Path(out).with_suffix('.manifest.json')
        if not checked and mp.exists() and mp.stat().st_mtime>=start-5:
            mf=json.loads(mp.read_text());ok=mf['runtime'].get('draft_kind')=='off' and mf['registry']['sha256']==sha(OVERLAY) and mf['sampling'].get('reasoning_effort')=='medium'
            log('C35 '+tag+' effort=medium draft=off fingerprint_ok='+str(ok));checked=True
            if not ok:d.kill();fail('manifest mismatch')
        c=worker_cmdline()
        if c and not worker_checked:
            ok=model in c and '--draft-kind' not in c and '--moe-expand' not in c and '"reasoning_effort": "medium"' in c
            log('WORKER '+tag+' medium/native/draftOFF='+str(ok));worker_checked=True
            if not ok:d.kill();fail('worker mismatch')
        if time.time()-last>=300:
            rs=read_rows(out);ws=[r['wall_s'] for r in rs];mean=statistics.mean(ws) if ws else None
            log('WATCH '+tag+' '+json.dumps({'n':len(rs),'total':22,'advance':len(rs)-previous,'pass':sum(bool(r.get('passed')) and not r.get('test_modified') for r in rs),'stalled':sum(r.get('stop_reason')=='stalled' for r in rs),'mean_s':mean,'remaining_mean_s':(22-len(rs))*mean if mean else None,'max_s':max(ws) if ws else None,'correction':'inspect flat counters against current request age; never kill on flatness alone'}));previous=len(rs);last=time.time()
        if time.time()-start>24*3600:d.kill();fail('24h stage backstop')
        time.sleep(10)
    if d.returncode:fail(tag+' rc='+str(d.returncode))
    if not checked:fail('manifest was not checked')
    rs=read_rows(out);bad=[r for r in rs if r.get('error') or str(r.get('note','')).startswith('skipped') or str(r.get('grade_tail','')).startswith('skipped')]
    if bad:fail('invalid/skipped rows')
    log('END '+tag+' n='+str(len(rs))+' pass='+str(sum(bool(r.get('passed')) and not r.get('test_modified') for r in rs)))
def main():
    log('SELFTEST authorized medium Go queue; two models, matched O39 set, random five-item pilot then 17')
    if sh(['pgrep','-f','[r]un.py generate|[r]un_opencode_probe.py']).stdout.strip():fail('another driver active')
    if sh(['docker','info']).returncode:fail('Docker unavailable')
    if sh([WD+'/o39/opencode-1.18.15/opencode','--version']).stdout.strip()!='1.18.15':fail('opencode pin mismatch')
    carrier=Path(REPO+'/benchmark/opencode_bench.json');cfg=json.loads(carrier.read_text())
    for m in MODELS:
        assert m in cfg['provider']['mlx-local']['models']
        assert not Path(REPO+'/benchmark/results/'+m+'/opencode_go.medium.jsonl').exists()
    user=Path.home()/'.config/opencode/opencode.json';backup=Path(OUT+'/go_medium_user_config.backup');existed=user.exists()
    if existed:shutil.copy2(user,backup)
    shutil.copy2(carrier,user)
    try:
        ensure_router(OVERLAY)
        for model in MODELS:
            unload()
            out=REPO+'/benchmark/results/'+model+'/opencode_go.medium.jsonl';tag='go_medium_'+model
            leg(model,PILOT,out,tag+'_pilot')
            rs=read_rows(out)
            if len(rs)!=5:fail('pilot count mismatch')
            log('PILOT SIZING '+model+' mean_s='+str(statistics.mean(r['wall_s'] for r in rs))+' max_s='+str(max(r['wall_s'] for r in rs)))
            leg(model,REST,out,tag+'_rest')
            if len(read_rows(out))!=22:fail('full count mismatch')
        log('=== MEDIUM GO DONE === assess both results and B ladder recommendations; no auto promotion')
    finally:
        if existed:shutil.copy2(backup,user)
        else:user.unlink(missing_ok=True)
        log('opencode user config restored')
if __name__=='__main__':
    try:main()
    except Exception as exc:log('FATAL '+repr(exc));raise
