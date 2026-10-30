"""P426 B2 frozen tests, delivery 1d: the operator email (spec v3.2 §11.3, §16.2 `harvest_wave2`, §16.5
`p426_harvest.Scrub(..., emails=(…))`, §16.6 `HarvestError`).

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant; [NEW] exercises new behaviour.
`harvest_wave2(leg_root, *, main_root, evidence_stage, scrub, secrets)` on a NOT_STARTED attempt (`b2_frozen_support`); the
operator's address and domain refuse, any other address goes to the local review file (post-reveal 3f). Every address here is a fake."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.tests import b2_frozen_support as S

OPERATOR = "op.erator@corp-mail.example"


def H():
    from bench import p426_harvest
    return p426_harvest


def harvest(tmp_path, runlog_extra):
    wd = tmp_path / "wd"
    leg = S.not_started_leg_root(wd)
    (leg / "RUNLOG.md").write_text((leg / "RUNLOG.md").read_text() + runlog_extra)
    h = H()
    scrub = h.Scrub(workdir=wd, repo=tmp_path / "repo", home=tmp_path / "home", user="b2opuser", hosts=("b2host",),
                    emails=(OPERATOR,))
    main, stage = tmp_path / "main", tmp_path / "stage"
    try:
        return h.harvest_wave2(leg, main_root=main, evidence_stage=stage, scrub=scrub, secrets={}), main, stage
    except h.HarvestError as e:                       # §16.6: a refusal raises HarvestError and publishes nothing
        return e, main, stage


def published_text(*roots):
    return "\n".join(p.read_text(errors="replace") for r in roots if Path(r).exists() for p in Path(r).rglob("*") if p.is_file())


@pytest.mark.parametrize("addr", [OPERATOR, "someone.else@corp-mail.example"])
def test_new_the_operators_address_and_domain_refuse(tmp_path, addr):
    res, main, stage = harvest(tmp_path, f"git author {addr}\n")
    assert isinstance(res, H().HarvestError)
    assert not (Path(main) / "benchmark/results/p426/wave2/tg1-p426-off-pilot.a1/HARVEST.json").exists()
    assert addr not in published_text(main, stage) and addr not in str(res)


def test_new_a_foreign_address_is_listed_for_review_and_published(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "wd"))          # 3f: the review file is written under $STACK_WORKDIR
    res, main, stage = harvest(tmp_path, "the model wrote maintainer@example.org\n")
    assert isinstance(res, dict), res
    # post-reveal 3f (§16.8 after the s9 delivery): `HARVEST.json` carries `review.emails_count` and the local review file's
    # portable path; the address itself is in `$STACK_WORKDIR/p426/review/<attempt>.emails.json` only (never under `main`)
    assert res["review"]["emails_count"] == 1 and "maintainer@example.org" not in json.dumps(res)
    review = tmp_path / "wd/p426/review/tg1-p426-off-pilot.a1.emails.json"
    assert "maintainer@example.org" in review.read_text()
    assert "maintainer@example.org" not in published_text(main)
    assert any(f.get("source") == "leg:RUNLOG.md" and f["destination"] == "evidence" for f in res["files"])


def test_inv_the_wave1_scrub_constructor_still_works_without_emails(tmp_path):
    s = H().Scrub(workdir=tmp_path / "wd", repo=tmp_path / "repo", home=tmp_path / "home", user="b2opuser", hosts=("b2host",))
    assert s.text(f"{tmp_path}/wd/x b2opuser@b2host") == "$STACK_WORKDIR/x <user>@localhost"
