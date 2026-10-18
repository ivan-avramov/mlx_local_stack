"""Chain operations the M64 arm schedule needs beyond `chain_ops.ChainOps` (spec 5.5, 8.1, 8.3): restart the shared search
service before every leg, reset the worker's cache session and send one unscored warm-up request at every arm switch.

None exists yet: the search service is build step D2 and the cache-session reset / warm-up need a worker control endpoint
in the `../mlx-vlm` fork (spec 7, a separate step). `UnavailableArmOps` is the clearly named stand-in: the REAL chain
(`M64ChainOps`) refuses at start (`require_arm_ops`) and again at each hook, so no leg can run without them. Tests inject
fakes with the same method names."""
from __future__ import annotations

from . import chain_ops as co


class ArmOpsUnavailable(co.ChainAbort):
    pass


MISSING = ("search_restart (D2: M64-owned SearXNG container, build step D2)",
           "reset_cache_session / warmup (a worker control endpoint in ../mlx-vlm, the fork step)")


class UnavailableArmOps:
    """Mixin for the real ChainOps: every M64 hook refuses."""

    def require_arm_ops(self):
        raise ArmOpsUnavailable("M64 chain operations are not built yet: " + "; ".join(MISSING))

    def search_restart(self, leg):
        self.require_arm_ops()

    def reset_cache_session(self, model):
        self.require_arm_ops()

    def warmup(self, model):
        self.require_arm_ops()


class M64ChainOps(UnavailableArmOps, co.ChainOps):
    """`ChainOps` for the M64 chain (out-root under `$STACK_WORKDIR/m64`)."""
