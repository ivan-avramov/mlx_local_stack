"""S26-P17: the KV panel export refused the real stage-3 A2 (cjudge) member — "packet leak (identity visible to a judge): …
family-token" — because 9 of 40 cjudge answers name model families as their topic ("Qwen2.5", "NVIDIA"; in 6 of the 9 only the N16  (allow-shorthand: quotes model output)
answer does, in none the prompt). Under the KV lever both arms are ONE registry entry, so a family token cannot tell a judge which arm
wrote an answer, and excluding such items would select on the arms' outputs (cold read Sol P1). The KV leak check no longer treats
`family-token` as a leak; the KV / arm identifiers, registry names and template tags still refuse."""
import hashlib
import json

import pytest

from bench import p426_panel as P
from bench import p426_verify as V
from bench.tests.test_m76_b3_impl_panel import JUDGES, Sources, _differ


class TokenPanel:
    """`test_m76_b3_impl_panel.Panel`'s world with one cjudge item's answer carrying `token` in the arms named by `arms`."""

    def __init__(self, tmp_path, monkeypatch, token, arms=("n16", "x")):
        from bench.tests.test_m76_b3_impl_verify import World

        w = World(tmp_path, monkeypatch, kinds=())
        target = {}

        def hook_for(arm):
            def hook(row):
                row = _differ(row) if arm == "x" else dict(row)
                if not target:
                    target["id"] = row["id"]
                if row["id"] == target["id"] and arm in arms:
                    row["content"] = row["content"] + f" Deploy it like {token} does."
                    if "content_sha256" in row:
                        row["content_sha256"] = hashlib.sha256(row["content"].encode()).hexdigest()
                return row
            return hook
        for label in ("b1", "b2"):
            for arm in ("n16", "x"):
                w.leg("cjudge", arm, label, row_hook=hook_for(arm))
        self.w, self.target = w, target
        b8 = V.verify_all_kv(w.rows, w.repo, ("n16", "x"), kinds=("cjudge",))
        self.b8_path = tmp_path / "B8.json"
        self.b8_path.write_text(V.dumps(b8))
        self.judges = tmp_path / "judges.json"
        self.judges.write_text(json.dumps(JUDGES))
        ids = w.ids["axes"]["cjudge"]["block1"] + w.ids["axes"]["cjudge"]["block2"]
        self.sources = Sources({str(i): f"Task {i}" for i in ids})
        self.out = tmp_path / "panel"
        self.out.mkdir()

    def export(self):
        return P.kv_export(self.w.rows, self.b8_path, self.judges, self.out, None, sources=self.sources, members=("A2",))


@pytest.mark.parametrize("arms", [("n16", "x"), ("n16",)])
def test_a_family_token_in_an_answer_is_content_and_every_item_is_exported(tmp_path, monkeypatch, arms):
    """[FIX] the real failure (both shapes seen: in both answers, and in N16's only): the member exports, nothing is excluded, and
    the judges see the answer as written."""
    tp = TokenPanel(tmp_path, monkeypatch, "Qwen2.5-Coder", arms=arms)
    done = tp.export()["A2"]
    assert done["counts"]["items"] == len(tp.w.ids["axes"]["cjudge"]["block1"]) * 2
    packets = list((tp.out / "A2").glob("*/batch*/p*.md"))
    assert any("qwen2.5-coder" in p.read_text().lower() for p in packets)


@pytest.mark.parametrize("token", ["<think>", "<|im_start|>", "the n16 arm", "tq4 attention", "kv_bits 4"])
def test_arm_and_serving_identifiers_still_refuse(tmp_path, monkeypatch, token):
    """[INV] a serving-path tag or an arm / KV identifier is an identity leak: the export refuses as before."""
    tp = TokenPanel(tmp_path, monkeypatch, token)
    with pytest.raises(V.RefusalError, match="packet leak"):
        tp.export()
    assert not (tp.out / "A2").exists()


def test_the_registry_name_still_refuses(tmp_path, monkeypatch):
    """[INV] the full registry name of the entry is a leak."""
    tp = TokenPanel(tmp_path, monkeypatch, "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed")
    with pytest.raises(V.RefusalError, match="packet leak"):
        tp.export()


# ---- S26-P17b: generic path / MTP patterns are content under the KV lever; the box's real home and username still refuse
@pytest.mark.parametrize("text", ["PATCH /api/admin/users/:id/role", "never write outside /home/dev/projects/*",  # allow-pii-pattern: a generic example path from a model answer
                                  "Speculative Decoding with an MTP Head", "a drafter model", "/private/tmp/build"])
def test_topical_paths_and_mtp_words_are_content_under_the_kv_lever(tmp_path, monkeypatch, text):
    """[FIX] the real second refusal (an API route matched /Users/ case-insensitively; a generic /home/ path; a question about MTP —
    both KV arms run MTP ON): exported as written."""
    tp = TokenPanel(tmp_path, monkeypatch, text, arms=("x",))
    assert tp.export()["A2"]["counts"]["items"] == len(tp.w.ids["axes"]["cjudge"]["block1"]) * 2


def test_the_boxs_real_home_path_and_username_still_refuse(tmp_path, monkeypatch):
    """[INV] the machine's own home path or username in an answer is a box identity (and PII): refuse."""
    import getpass
    from pathlib import Path
    for k, text in enumerate((str(Path.home()) + "/ws/project", "owned by " + getpass.getuser() + " on this box")):
        (tmp_path / f"case{k}").mkdir()
        tp = TokenPanel(tmp_path / f"case{k}", monkeypatch, text)
        with pytest.raises(V.RefusalError, match="packet leak"):
            tp.export()
