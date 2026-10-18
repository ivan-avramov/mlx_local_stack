"""P371 `Host` seam (plan 3.1): the client-neutral process helpers a shared core may call on the probe module `p`.

Everything else the pre-P371 item loop reads from `p` is corpus-specific (moves into `Corpus`), seed derivation (moves
into the core, R12) or opencode-specific (stays with the adapter); `NON_SEAM_HOST_USES` records that classification so a
new, unclassified `p.<name>` call in the item loop fails the drift test. This module imports nothing from the bench
package: it is pure data plus a checker, safe inside every probe's import closure."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

HOST_HELPERS = (
    "_scrub_pii", "_scrub_error", "_portable", "_sha_of", "_stack_workdir", "_prompt_date", "_scratch_dir",
    "_item_scratch_dir", "_fresh_tmpdir", "_git_init_scratch", "_freeze_mtimes",
)

# `p.<name>` uses of the pre-P371 item loop (`tg1_runner`) that are deliberately NOT part of the seam.
NON_SEAM_HOST_USES = (
    "__file__",                                                                   # entry identity (closure root)
    "_polyglot_root", "_polyglot_sha", "_prepare",                                # corpus (moves into Corpus)
    "_item_seed", "_seed_row_fields",                                             # seed derivation (moves into the core)
    "NORETRY_PLUGIN", "PINNED_OPENCODE_VERSION_V2", "SCAFFOLD_ENV_POLICY_V2",     # opencode adapter
    "_a4_receipt", "_carrier_selection", "_default_opencode_bin", "_make_run_dir", "_metric_export",
    "_opencode_env", "_parse_version", "_require_opencode_bin", "_seed_overlay", "_worker_load_identity",
    "loop_metrics", "traffic_metrics",
)


class HostSeamError(TypeError):
    """A probe module does not provide the client-neutral helpers the shared core needs."""


@runtime_checkable
class Host(Protocol):
    def _scrub_pii(self, *a, **k): ...
    def _scrub_error(self, *a, **k): ...
    def _portable(self, *a, **k): ...
    def _sha_of(self, *a, **k): ...
    def _stack_workdir(self, *a, **k): ...
    def _prompt_date(self, *a, **k): ...
    def _scratch_dir(self, *a, **k): ...
    def _item_scratch_dir(self, *a, **k): ...
    def _fresh_tmpdir(self, *a, **k): ...
    def _git_init_scratch(self, *a, **k): ...
    def _freeze_mtimes(self, *a, **k): ...


def require_host(p):
    """Return `p` when it provides every helper in `HOST_HELPERS` as a callable, else raise `HostSeamError` naming all
    the missing or non-callable ones."""
    bad = [name for name in HOST_HELPERS if not callable(getattr(p, name, None))]
    if bad:
        raise HostSeamError("probe module lacks the Host helper(s): " + ", ".join(bad))
    return p
