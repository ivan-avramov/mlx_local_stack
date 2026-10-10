import hashlib, json, math, os, random, re, shutil, signal, statistics, subprocess, sys, threading, time
from pathlib import Path
WD=os.environ['STACK_WORKDIR']; REPO=os.environ['STACK_REPO']; PY=f"{REPO}/.venv-bench/bin/python"
OUT=f"{WD}/queue"; OFF_OVERLAY=f"{OUT}/bench_overlay_q4.yaml"
LOG=open(f"{OUT}/m34c_pilot.log",'a',buffering=1)
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


def main():
    log('SELFTEST M34c bounded transfer pilot; 8 late MoE layers, top-k 6 to cap 15, threshold .8 decay .5')
    if sh(['pgrep','-f','[r]un.py generate']).stdout.strip():fail('another driver active')
    model='NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit'
    sets=json.loads(Path(OUT+'/m34c_pilot_ids.json').read_text())['sets']
    for bench in ['mbppplus','math500']:
        for label in ['nat','exp']:
            overlay=OUT+'/bench_overlay_q6_'+label+'.yaml'
            ensure_router(overlay)
            tune='m34cp'+label;tag='M34c_'+bench+'_'+label+'_pilot'
            extra=['--limit',bench+'=0','--ids',bench+'='+':'.join(sets[bench])]
            if run_generate(model,bench,tune,5,tag,overlay,extra=extra,samples=1,bound_h=12):fail(tag+' generation failed')
            s=summarize(model,bench,tune,5,tag)
            if s['n']!=5 or s['errors']:fail(tag+' incomplete/error rows')
    log('=== M34c PILOT GENERATION DONE ===')
    for bench in ['mbppplus','math500']:
        for label in ['nat','exp']:grade(model,bench,'m34cp'+label,'M34c_'+bench+'_'+label+'_pilot')
    log('=== M34c PILOT DONE === bounded pilot only; review before extension')
if __name__=='__main__':
    try:main()
    except Exception as exc:log('FATAL '+repr(exc));raise
