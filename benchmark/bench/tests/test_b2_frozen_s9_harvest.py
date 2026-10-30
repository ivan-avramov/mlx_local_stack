"""P426 B2 frozen tests, s9 harvest (spec v3.2 §11, §16.1 `HARVEST.json`, §16.2
`bench.p426_harvest wave2 --leg-root <dir> --main-root <checkout> --evidence-stage <dir>`).

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant; [NEW] exercises new behaviour.
The CLI runs as a subprocess from a scratch copy of the bench package with HOME / XDG_CONFIG_HOME / STACK_WORKDIR under
tmp_path; every secret is a fake. The clean leg is a NOT_STARTED attempt (§5.1: the sequencer's `leg.json` + the chain's
RUNLOG, nothing launched) — every leg state is harvested (§11.1). A refusal prints `REFUSED: <reason>` naming the file and
exits 2 (§16); a secret value is never printed or written."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from bench.tests import b2_frozen_support as S

LEG, ATTEMPT = "tg1-p426-off-pilot", 1
NAME = f"{LEG}.a{ATTEMPT}"


def world(tmp_path, **env_extra):
    repo = S.harvest_repo(tmp_path)
    env = S.harvest_env(tmp_path, env_extra=env_extra)
    leg = S.not_started_leg_root(env["STACK_WORKDIR"], LEG, ATTEMPT)
    return repo, env, leg


def harvest(tmp_path, repo, env, leg):
    return S.run_harvest(repo, leg, env, main_root=tmp_path / "main", stage=tmp_path / "stage")


def out(got):
    return got.stdout + got.stderr


def refused_lines(got):
    return [ln for ln in out(got).splitlines() if "REFUSED: " in ln]


def harvest_json(tmp_path):
    p = tmp_path / "main" / "benchmark/results/p426/wave2" / NAME / "HARVEST.json"
    return json.loads(p.read_text()) if p.exists() else None


def assert_refused_naming(got, rel):
    assert got.returncode == 2 and refused_lines(got), out(got)[-2000:]
    assert any(rel in ln for ln in refused_lines(got)), refused_lines(got)


def assert_never_written(tmp_path, got, value, sources):
    assert value not in out(got)
    assert value not in S.all_output_text(tmp_path, exclude=sources)


def entry_for(doc, rel):
    """[d2] §16.4: an entry is keyed by a typed `source`; a leg-root file is `leg:<path relative to the leg root>`."""
    return [f for f in doc["files"] if f.get("source") == "leg:" + rel]


SOURCE_TYPES = ("leg:", "run:", "evidence:", "record:", "log:")


# ------------------------------------------------------------------------------------------------ a clean leg
def test_new_a_not_started_attempt_is_harvested_with_a_self_hashed_harvest_json(tmp_path):
    repo, env, leg = world(tmp_path)
    got = harvest(tmp_path, repo, env, leg)
    assert got.returncode == 0, out(got)[-2000:]
    doc = harvest_json(tmp_path)
    assert doc is not None and doc["state"] == "NOT_STARTED" and doc["leg"] == LEG and doc["attempt"] == ATTEMPT
    assert S.self_hashed(doc)["sha256"] == doc["sha256"]
    (legrec,) = entry_for(doc, "leg.json")
    (runlog,) = entry_for(doc, "RUNLOG.md")
    assert legrec["destination"] == "main" and runlog["destination"] == "evidence"
    assert legrec["sha256"] == S.sha256_file(leg / "leg.json")
    assert {f["destination"] for f in doc["files"]} <= {"main", "evidence", "excluded"}


def test_new_a_harvest_whose_destination_verifies_is_done_and_idempotent(tmp_path):
    repo, env, leg = world(tmp_path)
    assert harvest(tmp_path, repo, env, leg).returncode == 0
    p = tmp_path / "main" / "benchmark/results/p426/wave2" / NAME / "HARVEST.json"
    assert p.is_file(), "the first harvest published no HARVEST.json"
    before = p.read_bytes()
    again = harvest(tmp_path, repo, env, leg)
    assert again.returncode == 0 and p.read_bytes() == before


def test_inv_the_leg_root_is_never_modified_by_its_harvest(tmp_path):
    repo, env, leg = world(tmp_path)
    snap = {p.relative_to(leg): p.read_bytes() for p in leg.rglob("*") if p.is_file()}
    harvest(tmp_path, repo, env, leg)
    assert {p.relative_to(leg): p.read_bytes() for p in leg.rglob("*") if p.is_file()} == snap


# ------------------------------------------------------------------------------------------------ inventory and symlinks
def test_new_an_unmatched_file_fails_the_harvest(tmp_path):
    repo, env, leg = world(tmp_path)
    (leg / "stray.unknown-kind").write_text("x")
    assert_refused_naming(harvest(tmp_path, repo, env, leg), "stray.unknown-kind")


def test_new_a_symlink_outside_a_final_tree_fails_the_harvest_without_being_followed(tmp_path):
    repo, env, leg = world(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("SENTINEL-CONTENT-NEVER-READ")
    (leg / "linked.log").symlink_to(outside)
    got = harvest(tmp_path, repo, env, leg)
    assert_refused_naming(got, "linked.log")
    assert_never_written(tmp_path, got, "SENTINEL-CONTENT-NEVER-READ", [outside])


def test_new_a_symlink_inside_a_final_tree_is_excluded_as_symlink_never_followed(tmp_path):
    repo, env, leg = world(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("SENTINEL-CONTENT-NEVER-READ")
    tree = leg / "transcripts" / "python__beer-song.final_tree"
    tree.mkdir(parents=True)
    (tree / "solution.py").write_text("answer = 42\n")
    (tree / "link_to_outside").symlink_to(outside)
    got = harvest(tmp_path, repo, env, leg)
    doc = harvest_json(tmp_path)
    assert doc is not None or refused_lines(got), out(got)[-2000:]                     # the harvest did run
    assert not any("link_to_outside" in ln for ln in refused_lines(got))                # not a failure by itself
    if doc is not None:
        (link,) = entry_for(doc, "transcripts/python__beer-song.final_tree/link_to_outside")
        assert link["destination"] == "excluded" and link["exclusion_reason"] == "symlink"
    assert_never_written(tmp_path, got, "SENTINEL-CONTENT-NEVER-READ", [outside])


# ------------------------------------------------------------------------------------------------ the secret gate
@pytest.mark.parametrize("source", ["hftoken", "hf_cache_token", "machine_config", "environment"])
def test_new_an_exact_secret_value_quarantines_the_file_without_printing_it(tmp_path, source):
    """§11.3: the exact values of the credential sources, in memory; a 40-character token in a raw stream quarantines it."""
    secret = S.FAKE_SECRET_40
    repo, env, leg = world(tmp_path, **({"P426_TEST_API_KEY": secret} if source == "environment" else {}))
    home = tmp_path / "home"
    sources = []
    if source == "hftoken":
        sources.append(home / ".hftoken")
    elif source == "hf_cache_token":
        sources.append(home / ".cache/huggingface/token")
    elif source == "machine_config":
        sources.append(home / ".config/mlx_local_stack/config.sh")
    for p in sources:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f'export HF_TOKEN="{secret}"\n' if source == "machine_config" else secret)
    runlog = leg / "RUNLOG.md"
    runlog.write_text(runlog.read_text() + f"probe stderr: token {secret}\n")
    got = harvest(tmp_path, repo, env, leg)
    assert_refused_naming(got, "RUNLOG.md")
    assert_never_written(tmp_path, got, secret, sources + [runlog])


@pytest.mark.parametrize("value", [S.FAKE_HF_TOKEN_FILE, "sk-" + "s" * 40, "ghp_" + "R" * 36, "AKIA" + "Z" * 16,
                                   "-----BEGIN " + "RSA PRIVATE KEY-----", "Authorization: Bearer " + "b" * 32],
                         ids=["hf", "sk", "ghp", "akia", "pem", "bearer"])
def test_new_a_credential_format_quarantines_the_file_without_printing_it(tmp_path, value):
    repo, env, leg = world(tmp_path)
    runlog = leg / "RUNLOG.md"
    runlog.write_text(runlog.read_text() + f"captured: {value}\n")
    got = harvest(tmp_path, repo, env, leg)
    assert_refused_naming(got, "RUNLOG.md")
    assert_never_written(tmp_path, got, value, [runlog])


def test_new_placeholders_short_values_and_allowlisted_keys_never_quarantine(tmp_path):
    """§13: `TOKENIZERS_PARALLELISM=false` and a `1`-valued `*KEY*` variable never quarantine anything."""
    repo, env, leg = world(tmp_path, TOKENIZERS_PARALLELISM="false", SOME_FEATURE_KEY="1", SHORT_TOKEN="abc")
    cfg = tmp_path / "home/.config/mlx_local_stack/config.sh"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text('export TOKENIZERS_PARALLELISM=false\nexport SOME_FEATURE_KEY=1\n')
    runlog = leg / "RUNLOG.md"
    runlog.write_text(runlog.read_text() + "TOKENIZERS_PARALLELISM=false keys=1 tokens=abc ok=true\n")
    got = harvest(tmp_path, repo, env, leg)
    assert got.returncode == 0 and not refused_lines(got), out(got)[-2000:]
    doc = harvest_json(tmp_path)
    assert doc is not None, "no HARVEST.json published"
    (entry,) = entry_for(doc, "RUNLOG.md")
    assert entry["destination"] == "evidence"


def test_new_a_listed_secret_file_that_exists_but_cannot_be_read_refuses(tmp_path):
    repo, env, leg = world(tmp_path)
    token = tmp_path / "home" / ".hftoken"
    token.write_text(S.FAKE_SECRET_40)
    os.chmod(token, 0)
    try:
        got = harvest(tmp_path, repo, env, leg)
    finally:
        os.chmod(token, 0o600)
    assert_refused_naming(got, ".hftoken")
    assert S.FAKE_SECRET_40 not in out(got)


def test_new_a_foreign_email_is_listed_for_review_never_refused(tmp_path):
    repo, env, leg = world(tmp_path)
    runlog = leg / "RUNLOG.md"
    runlog.write_text(runlog.read_text() + "the model wrote maintainer@example.org into a comment\n")
    got = harvest(tmp_path, repo, env, leg)
    assert got.returncode == 0 and not refused_lines(got), out(got)[-2000:]
    doc = harvest_json(tmp_path)
    # post-reveal 3f (§16.8 after the s9 delivery): the address goes to the local review file only; `HARVEST.json` (a public
    # `main` record) carries `review.emails_count` and that file's portable path, never an address
    assert doc is not None and doc["review"]["emails_count"] == 1
    review = Path(env["STACK_WORKDIR"]) / "p426/review" / f"{NAME}.emails.json"
    assert f"$STACK_WORKDIR/p426/review/{NAME}.emails.json" in json.dumps(doc["review"])
    assert "maintainer@example.org" in review.read_text() and "maintainer@example.org" not in out(got)
    main = tmp_path / "main"
    assert not any("maintainer@example.org" in p.read_text(errors="replace") for p in main.rglob("*") if p.is_file())
    (entry,) = entry_for(doc, "RUNLOG.md")
    assert entry["destination"] == "evidence"


def test_new_the_sequencers_launch_log_is_inventoried_and_routed_to_evidence(tmp_path):
    """post-reveal 3f (§16.8 after the s9 delivery): the launch log lives at `<out-base>/logs/<attempt>.stdout`, never in
    the out-root; the harvest inventories it and routes it to `evidence`. The source's type prefix is left to the candidate."""
    repo, env, leg = world(tmp_path)
    log = leg.parent / "logs" / f"{NAME}.stdout"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("launch stdout line\n")
    got = harvest(tmp_path, repo, env, leg)
    assert got.returncode == 0, out(got)[-2000:]
    doc = harvest_json(tmp_path)
    (entry,) = [f for f in doc["files"] if str(f["source"]).endswith(f"logs/{NAME}.stdout")]
    assert entry["destination"] == "evidence" and str(entry["source"]).startswith(SOURCE_TYPES)
    assert entry["sha256"] == S.sha256_file(log)
    assert (tmp_path / "stage" / entry["published"]).is_file()           # the published name is the candidate's (§16.1 `published`)
    assert not (tmp_path / "main" / entry["published"]).exists()


def test_new_every_harvest_source_is_typed(tmp_path):
    repo, env, leg = world(tmp_path)
    assert harvest(tmp_path, repo, env, leg).returncode == 0
    doc = harvest_json(tmp_path)
    assert doc is not None and doc["files"] and all(str(f["source"]).startswith(SOURCE_TYPES) for f in doc["files"])


def test_new_a_retry_discards_only_this_attempts_incomplete_destination_and_commits(tmp_path):
    """[d2] §11.2: the `main` destination carrying `HARVEST.json` is the single commit point; a retry finding it without a
    verifying `HARVEST.json` deletes that attempt's incomplete destinations and stages, never another attempt's."""
    repo, env, leg = world(tmp_path)
    wave2 = tmp_path / "main" / "benchmark/results/p426/wave2"
    mine, other = wave2 / NAME, wave2 / f"{LEG}.a2"
    mine.mkdir(parents=True)
    (mine / "leg.json").write_text("{\"partial\": true}")                 # an interrupted earlier publication, no HARVEST.json
    other.mkdir(parents=True)
    (other / "chain.json").write_text("{\"other attempt\": true}")
    got = harvest(tmp_path, repo, env, leg)
    assert got.returncode == 0, out(got)[-2000:]
    doc = harvest_json(tmp_path)
    assert doc is not None and S.self_hashed(doc)["sha256"] == doc["sha256"]
    assert json.loads((mine / "leg.json").read_text()) == json.loads((leg / "leg.json").read_text())
    assert (other / "chain.json").read_text() == "{\"other attempt\": true}" and not (other / "HARVEST.json").exists()


def test_new_a_main_record_with_an_absolute_path_fails_the_harvest(tmp_path):
    """[d2] §11.2: records destined for `main` are portable at creation, so the scrub is byte-identity on them; a scrub
    change to a `main` record fails the harvest."""
    repo, env, leg = world(tmp_path)
    rec = json.loads((leg / "leg.json").read_text())
    rec["reason"] = "power: 96 W (see " + str(leg / "RUNLOG.md") + ")"
    (leg / "leg.json").write_text(json.dumps(S.self_hashed(rec)))       # post-reveal 3h: re-sealed, so only the path is wrong
    got = harvest(tmp_path, repo, env, leg)
    assert_refused_naming(got, "leg.json")
    assert harvest_json(tmp_path) is None


# ------------------------------------------------------------------------------------------------ post-reveal 3h (§16.8)
RUN_ID = "20261027T000000-0123456789ab"


def invalid_leg(tmp_path, *, runs=1, dnf_sidecar=None, dnf_ready="sealed"):
    """post-reveal 3h: an INVALID attempt (launched, then stopped; no barrier, no `invalidate`) whose one probe manifest names
    run `RUN_ID`; `runs` = how many run directories that id resolves to under `$STACK_WORKDIR`. With `dnf_sidecar` (a dict
    of changes) the chain recorded one `p426_dnf` entry whose sidecar differs from it by those changes ({} = equal).
    post-reveal 3i (§16.8 after the strict verify round 3): the DNF is also a ledger entry with its ready record —
    `dnf_ready` = "sealed" (the item record's `ready_sha256` is its self-hash), "missing", "unsealed" or "other-hash"."""
    repo, env, _ = world(tmp_path)
    wd = Path(env["STACK_WORKDIR"])
    leg = wd / "p426" / "wave2" / f"{LEG}.a2"
    (leg / "pilot").mkdir(parents=True)
    chain = dict(status="aborted", rc=2, p426_ledger=[], p426_invalid=[], p426_dnf=[], progress=dict(invocations=[]))
    if dnf_sidecar is not None:
        from bench import chain_rows as cr
        slot = "pilot|python|p2"
        sf = cr.slot_file(slot)
        (leg / "items").mkdir()
        ready = S.self_hashed(dict(slot=slot, item="python/p2", k=0))
        if dnf_ready != "missing":
            body = {k: v for k, v in ready.items() if k != "sha256"} if dnf_ready == "unsealed" else ready
            (leg / "items" / f"{sf}.ready.json").write_text(json.dumps(body))
        item = S.self_hashed(dict(slot=slot, verdict="reconciled", case="dnf_boundary", requests=[],
                                  ready_sha256="0" * 64 if dnf_ready == "other-hash" else ready["sha256"]))
        (leg / "items" / f"{sf}.dnf.json").write_text(json.dumps(item))
        chain["p426_ledger"] = [dict(slot=slot, kind="dnf", invocation=0, index=0)]
        entry = S.self_hashed(dict(slot=slot, item="python/p2", session="pilot", language="python", seed=1001, arm="off",
                                   pick=S.MODEL, load=0, load_gen=1, attempt=2, invocation=0,
                                   abort=dict(cause="connection", error="x"), item_record=f"items/{sf}.dnf.json"))
        chain["p426_dnf"] = [entry]
        side = S.self_hashed(dict({k: v for k, v in entry.items() if k != "sha256"}, **dnf_sidecar))
        (leg / "pilot" / "p426_dnf").mkdir()
        (leg / "pilot" / "p426_dnf" / f"{sf}.json").write_text(json.dumps(side))
    (leg / "chain.json").write_text(json.dumps(chain))
    (leg / "leg.json").write_text(json.dumps(S.self_hashed({"leg": LEG, "attempt": 2, "state": "INVALID", "class": "systemic",
                                                           "reason": "stopped", "chain_rc": 2})))
    (leg / "RUNLOG.md").write_text("STOP\n")
    (leg / "pilot" / f"{S.MODEL}.pilot.opencode_python.manifest.json").write_text(json.dumps(dict(run_id=RUN_ID)))
    for n in range(runs):
        (wd / f"opencode-probe-{n}" / f"run-{RUN_ID}").mkdir(parents=True)
    return repo, env, leg


def harvest_json_of(tmp_path, name):
    p = tmp_path / "main" / "benchmark/results/p426/wave2" / name / "HARVEST.json"
    return json.loads(p.read_text()) if p.exists() else None


def test_new_an_immutable_record_without_its_sha256_fails_the_harvest(tmp_path):
    """post-reveal 3h (§16.8 after the strict verify round 1): a missing hash fails the harvest like a wrong one."""
    repo, env, leg = world(tmp_path)
    rec = {k: v for k, v in json.loads((leg / "leg.json").read_text()).items() if k != "sha256"}
    (leg / "leg.json").write_text(json.dumps(rec))
    assert_refused_naming(harvest(tmp_path, repo, env, leg), "leg.json")
    assert harvest_json(tmp_path) is None


def test_new_a_manifest_run_id_resolving_to_one_run_directory_harvests(tmp_path):
    """The positive control of the two refusals below (post-reveal 3h)."""
    repo, env, leg = invalid_leg(tmp_path, runs=1)
    got = harvest(tmp_path, repo, env, leg)
    assert got.returncode == 0, out(got)[-2000:]
    assert harvest_json_of(tmp_path, leg.name)["state"] == "INVALID"


@pytest.mark.parametrize("runs", [0, 2], ids=["none", "two"])
def test_new_a_manifest_run_id_resolving_to_no_or_two_directories_fails_the_harvest(tmp_path, runs):
    """post-reveal 3h (§16.8): a manifest run id resolving to no run / evidence directory, or to more than one, fails."""
    repo, env, leg = invalid_leg(tmp_path, runs=runs)
    got = harvest(tmp_path, repo, env, leg)
    assert_refused_naming(got, "manifest.json")
    assert harvest_json_of(tmp_path, leg.name) is None


@pytest.mark.parametrize("change,ok", [({}, True), ({"load_gen": 7}, False)], ids=["equal", "differs"])
def test_new_a_chain_json_dnf_entry_must_equal_its_sidecar(tmp_path, change, ok):
    """post-reveal 3h (§16.8): `chain.json`'s `p426_dnf` entries equal their sidecars."""
    repo, env, leg = invalid_leg(tmp_path, dnf_sidecar=change)
    got = harvest(tmp_path, repo, env, leg)
    if ok:
        assert got.returncode == 0, out(got)[-2000:]
    else:
        assert_refused_naming(got, "p426_dnf")
        assert harvest_json_of(tmp_path, leg.name) is None


@pytest.mark.parametrize("ready", ["missing", "unsealed", "other-hash"])
def test_new_a_dnf_ledger_entry_needs_its_sealed_ready_record_named_by_ready_sha256(tmp_path, ready):
    """post-reveal 3i (§16.8 after the strict verify round 3): every ledger entry, DNF included, requires
    `items/<slot>.ready.json` with a valid self-hash, and its item record's `ready_sha256` equals it (the `equal` case of
    the sidecar test above is the positive control)."""
    repo, env, leg = invalid_leg(tmp_path, dnf_sidecar={}, dnf_ready=ready)
    got = harvest(tmp_path, repo, env, leg)
    assert got.returncode == 2 and refused_lines(got), out(got)[-2000:]
    assert any(".ready.json" in ln or "ready_sha256" in ln for ln in refused_lines(got)), refused_lines(got)
    assert harvest_json_of(tmp_path, leg.name) is None


def test_new_a_non_utf8_evidence_file_is_scrubbed_scanned_and_marked_lossy(tmp_path):
    """post-reveal 3h (§16.8): a non-UTF-8 evidence file is scrubbed and scanned via `surrogateescape` and marked
    `lossy_decode`; its workdir path is scrubbed, and a credential in it still quarantines."""
    repo, env, leg = world(tmp_path)
    wd = env["STACK_WORKDIR"]
    (leg / "RUNLOG.md").write_bytes(b"stopped \xff\xfe at " + f"{wd}/p426/x".encode() + b"\n")
    got = harvest(tmp_path, repo, env, leg)
    assert got.returncode == 0, out(got)[-2000:]
    (entry,) = entry_for(harvest_json(tmp_path), "RUNLOG.md")
    assert entry["destination"] == "evidence" and entry.get("lossy_decode")
    published = (tmp_path / "stage" / entry["published"]).read_bytes()
    assert wd.encode() not in published and b"$STACK_WORKDIR/p426/x" in published


def test_new_a_credential_in_a_non_utf8_evidence_file_still_quarantines(tmp_path):
    repo, env, leg = world(tmp_path)
    (leg / "RUNLOG.md").write_bytes(b"\xff\xfe key " + S.FAKE_HF_TOKEN_FILE.encode() + b"\n")
    got = harvest(tmp_path, repo, env, leg)
    assert_refused_naming(got, "RUNLOG.md")
    assert S.FAKE_HF_TOKEN_FILE not in out(got) and harvest_json(tmp_path) is None


# ------------------------------------------------------------------------------------------------ publish_* (§11.2, §16.7)
def H():
    from bench import p426_harvest
    return p426_harvest
WAVE2 = "benchmark/results/p426/wave2"


def scrub_for(tmp_path):
    return H().Scrub(workdir=tmp_path / "wd", repo=tmp_path / "repo", home=tmp_path / "home", user="b2opuser",
                     hosts=("b2host",), emails=("op.erator@corp-mail.example",))


def a_dossier(tmp_path, **over):
    doc = dict(pair="pilot", arms={"off": {"attempt": "tg1-p426-off-pilot.a1", "receipt_sha256": "1" * 64, "harvest_sha256": "2" * 64},
                                   "on": {"attempt": "tg1-p426-on-pilot.a1", "receipt_sha256": "3" * 64, "harvest_sha256": "4" * 64}},
               differences=[{"process": "worker", "field": "argv", "off": None, "on": "--draft-kind mtp"}], verdict="PASS",
               at="2026-10-27T00:00:00Z")
    doc.update(over)
    return S.write_record(tmp_path / "wd/p426/wave2/pairs/pilot__off-a1__on-a1.json", S.self_hashed(doc))


def assert_published(res, sources):
    """§16.7 (1g tail): `{published: [{source, destination, sha256}], harvest_sha256}`; one entry per source file, its
    sha256 the published bytes' (byte-identical to the source)."""
    assert set(res) >= {"published", "harvest_sha256"}, res
    by_name = {Path(str(e["destination"])).name: e for e in res["published"]}
    for s in sources:
        e = by_name[Path(s).name]
        assert set(e) >= {"source", "destination", "sha256"} and e["sha256"] == S.sha256_file(s)
    return True


def test_new_publish_dossier_publishes_the_dossier_byte_identical_to_main_pairs_and_is_idempotent(tmp_path):
    """§16.7: `p426_harvest.publish_dossier(path, *, main_root, evidence_stage, scrub) -> dict` to
    `benchmark/results/p426/wave2/pairs/` (§6.5, §11.2), staged and verified like a leg's `main` destination."""
    src = a_dossier(tmp_path)
    main, stage = tmp_path / "main", tmp_path / "stage"
    res = H().publish_dossier(src, main_root=main, evidence_stage=stage, scrub=scrub_for(tmp_path))
    dst = main / WAVE2 / "pairs" / src.name
    assert dst.read_bytes() == src.read_bytes()
    assert_published(res, [src])
    again = H().publish_dossier(src, main_root=main, evidence_stage=stage, scrub=scrub_for(tmp_path))
    assert_published(again, [src]) and dst.read_bytes() == src.read_bytes()


def test_new_publish_dossier_refuses_a_dossier_the_scrub_would_change_and_publishes_nothing(tmp_path):
    """§11.2: a record destined for `main` is portable at creation; a scrub change to it fails (HarvestError, §16.6)."""
    src = a_dossier(tmp_path, verdict="PASS (see " + str(tmp_path / "wd/p426/wave2/RUNLOG.md") + ")")
    main = tmp_path / "main"
    with pytest.raises(H().HarvestError):
        H().publish_dossier(src, main_root=main, evidence_stage=tmp_path / "stage", scrub=scrub_for(tmp_path))
    assert not (main / WAVE2 / "pairs" / src.name).exists()


def test_new_publish_run_files_publishes_each_file_to_main_wave2_run(tmp_path):
    """§16.7: `publish_run_files(paths, *, main_root, scrub) -> dict`; `paths` are files (the frozen records and
    `sequence.json`), published to `benchmark/results/p426/wave2/run/` byte-identical."""
    rec = tmp_path / "wd/p426/records"
    v8 = S.write_record(rec / "v8_base.json", S.v8_base(off_worktree="$STACK_WORKDIR/stack-p426-off",    # portable (§11.2)
                                                         on_worktree="$STACK_WORKDIR/stack-p426-on"))
    am = S.write_record(rec / "amendment.json", S.timeout_amendment(v8))
    seqf = tmp_path / "wd/p426/wave2/sequence.json"
    seqf.parent.mkdir(parents=True, exist_ok=True)
    seqf.write_text(json.dumps({"legs": [{"leg": LEG, "attempt": 1, "state": "VALID"}], "pairs": [], "previous_sha256": None}))
    main = tmp_path / "main"
    res = H().publish_run_files([v8, am, seqf], main_root=main, scrub=scrub_for(tmp_path))
    assert_published(res, [v8, am, seqf])
    for f in (v8, am, seqf):
        assert (main / WAVE2 / "run" / f.name).read_bytes() == f.read_bytes()


def test_new_publish_run_files_refuses_a_run_file_the_scrub_would_change_and_publishes_nothing(tmp_path):
    seqf = tmp_path / "wd/p426/wave2/sequence.json"
    seqf.parent.mkdir(parents=True)
    seqf.write_text(json.dumps({"legs": [], "pairs": [], "previous_sha256": None, "note": str(tmp_path / "wd/p426/x")}))
    main = tmp_path / "main"
    with pytest.raises(H().HarvestError):
        H().publish_run_files([seqf], main_root=main, scrub=scrub_for(tmp_path))
    assert not (main / WAVE2 / "run" / "sequence.json").exists()


# ------------------------------------------------------------------------------------------------ post-reveal 3i (§16.8)
def _unsealed(path, *, wrong=False):
    doc = json.loads(Path(path).read_text())
    if wrong:
        doc["sha256"] = "0" * 64
    else:
        doc.pop("sha256", None)
    Path(path).write_text(json.dumps(doc, sort_keys=True, indent=1))
    return path


def _run_files(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "wd"))           # the manifest's out_root is written portable
    rec = tmp_path / "wd/p426/records"
    v8 = S.write_record(rec / "v8_base.json", S.v8_base(off_worktree="$STACK_WORKDIR/stack-p426-off",
                                                         on_worktree="$STACK_WORKDIR/stack-p426-on"))
    return {"v8_base.json": v8, "amendment.json": S.write_record(rec / "amendment.json", S.timeout_amendment(v8)),
            "rehearsal.json": S.write_record(rec / "rehearsal.json", S.rehearsal_manifest(tmp_path / "wd/p426/rehearsal/r1"))}


def test_new_publish_run_files_publishes_the_sealed_immutable_run_files(tmp_path, monkeypatch):
    """The positive control of the refusals below (post-reveal 3i)."""
    files = _run_files(tmp_path, monkeypatch)
    res = H().publish_run_files(list(files.values()), main_root=tmp_path / "main", scrub=scrub_for(tmp_path))
    assert_published(res, list(files.values()))


@pytest.mark.parametrize("which", ["v8_base.json", "amendment.json", "rehearsal.json"])
@pytest.mark.parametrize("wrong", [False, True], ids=["missing", "wrong"])
def test_new_publish_run_files_refuses_an_immutable_run_file_without_a_valid_self_hash(tmp_path, monkeypatch, which, wrong):
    """post-reveal 3i (§16.8 after the strict verify round 2): every published immutable run file (v8 base, amendment,
    rehearsal manifest) needs a valid self-hash; nothing is published."""
    files = _run_files(tmp_path, monkeypatch)
    _unsealed(files[which], wrong=wrong)
    main = tmp_path / "main"
    with pytest.raises(H().HarvestError) as e:
        H().publish_run_files(list(files.values()), main_root=main, scrub=scrub_for(tmp_path))
    assert which in str(e.value)
    assert not (main / WAVE2 / "run").exists() or not any((main / WAVE2 / "run").iterdir())


def test_new_publish_run_files_publishes_an_unsealed_sequence_json(tmp_path):
    """post-reveal 3i (§16.8): only `sequence.json` is exempt from the self-hash rule."""
    seqf = tmp_path / "wd/p426/wave2/sequence.json"
    seqf.parent.mkdir(parents=True)
    seqf.write_text(json.dumps({"legs": [], "pairs": [], "previous_sha256": None}))
    main = tmp_path / "main"
    assert_published(H().publish_run_files([seqf], main_root=main, scrub=scrub_for(tmp_path)), [seqf])


@pytest.mark.parametrize("wrong", [False, True], ids=["missing", "wrong"])
def test_new_publish_dossier_refuses_a_dossier_without_a_valid_self_hash(tmp_path, wrong):
    src = _unsealed(a_dossier(tmp_path), wrong=wrong)
    main = tmp_path / "main"
    with pytest.raises(H().HarvestError):
        H().publish_dossier(src, main_root=main, evidence_stage=tmp_path / "stage", scrub=scrub_for(tmp_path))
    assert not (main / WAVE2 / "pairs" / src.name).exists()


def test_new_publication_quarantines_an_exact_credential_value_without_printing_it(tmp_path, capsys):
    """post-reveal 3i (§16.8): publication runs the leg harvest's gate, the exact in-memory credential values included. §16.8
    does not name how the values reach `publish_*` (§16.7 pins their signatures without them); the candidate carries them in
    `Scrub(…, secrets=…)` — a (d) name, used here as the candidate's. A clean twin publishes (the control)."""
    from dataclasses import replace
    scrub = replace(scrub_for(tmp_path), secrets={"HF_TOKEN": S.FAKE_SECRET_40})
    main = tmp_path / "main"
    clean = a_dossier(tmp_path)
    assert H().publish_dossier(clean, main_root=main, evidence_stage=tmp_path / "stage", scrub=scrub)["published"]
    src = S.write_record(tmp_path / "wd/p426/wave2/pairs/s1__off-a1__on-a1.json", S.self_hashed(dict(
        json.loads(clean.read_text()), pair="s1", differences=[{"process": "worker", "field": "env.NOTE", "off": None,
                                                                 "on": "see " + S.FAKE_SECRET_40}])))
    with pytest.raises(H().HarvestError) as e:
        H().publish_dossier(src, main_root=main, evidence_stage=tmp_path / "stage", scrub=scrub)
    assert S.FAKE_SECRET_40 not in str(e.value) and S.FAKE_SECRET_40 not in "".join(capsys.readouterr())
    assert not (main / WAVE2 / "pairs" / src.name).exists()


def test_new_publication_never_follows_an_existing_stage_path(tmp_path):
    """post-reveal 3i (§16.8 after the strict verify round 3): a record is staged with `O_CREAT | O_EXCL | O_NOFOLLOW`; an
    existing stage path refuses, never followed or reused. The stage name `<destination>.stage` is the candidate's (§11.2
    says only "beside each destination")."""
    src = a_dossier(tmp_path)
    main = tmp_path / "main"
    dst = main / WAVE2 / "pairs" / src.name
    dst.parent.mkdir(parents=True)
    victim = tmp_path / "victim.txt"
    victim.write_text("untouched\n")
    (dst.parent / (dst.name + ".stage")).symlink_to(victim)
    with pytest.raises(H().HarvestError):
        H().publish_dossier(src, main_root=main, evidence_stage=tmp_path / "stage", scrub=scrub_for(tmp_path))
    assert victim.read_text() == "untouched\n" and not dst.exists()


def test_inv_the_wave1_harvest_module_keeps_its_entry_points():
    from bench import p426_harvest as h
    assert callable(h.harvest) and callable(h.harvest_run_files) and h.WAVE1.as_posix() == "benchmark/results/p426/wave1"
    assert callable(h.Scrub)
