"""M76 B7 red-first golden: `paired_delta`'s default output on fixed inputs, frozen from the pre-B7 code (stack e92418b5).

The repr strings below were captured by running today's `paired_delta` before any B7 change; equality of the repr pins
key order, values and float bits.
"""
import bench.stats as S

A = {f"i{j:02d}": [1, 0, 1] if j % 3 else [0, 0, 1] for j in range(20)}
B = {f"i{j:02d}": [1, 1, 0] if j % 4 else [0, 1, 0] for j in range(20)}
A1 = {f"i{j:02d}": [1] for j in range(12)}
B1 = {f"i{j:02d}": [1] for j in range(12)}
STRATA = {f"i{j:02d}": j % 2 for j in range(20)}

GOLDEN = {
    "plain": "{'delta': -0.033333333333333215, 'lo': -0.2166666666666667, 'hi': 0.16666666666666652, 'verdict': 'wash', "
             "'n_items': 20, 'mde': 0.28015850000000003, 'degenerate': False, 'discordance_upper95': None, "
             "'directional': 'b'}",
    "strata": "{'delta': -0.033333333333333215, 'lo': -0.23333333333333323, 'hi': 0.15, 'verdict': 'wash', "
              "'n_items': 20, 'mde': 0.28015850000000003, 'degenerate': False, 'discordance_upper95': None, "
              "'directional': 'b'}",
    "degenerate": "{'delta': 0.0, 'lo': 0.0, 'hi': 0.0, 'verdict': 'wash', 'n_items': 12, 'mde': 0.3616830682661502, "
                  "'degenerate': True, 'discordance_upper95': 0.22092219194555585, 'directional': 'tie'}",
}


def test_paired_delta_default_output_golden():
    assert repr(S.paired_delta(A, B, iters=2000, seed=426)) == GOLDEN["plain"]
    assert repr(S.paired_delta(A, B, iters=2000, seed=7, strata=STRATA)) == GOLDEN["strata"]
    assert repr(S.paired_delta(A1, B1, iters=500, seed=426)) == GOLDEN["degenerate"]


def test_paired_delta_explicit_default_alphas_equal_golden():
    assert repr(S.paired_delta(A, B, iters=2000, seed=426, interval_alpha=0.05, exact_alpha=0.05)) == GOLDEN["plain"]
    assert repr(S.paired_delta(A1, B1, iters=500, seed=426, interval_alpha=0.05, exact_alpha=0.05)) \
        == GOLDEN["degenerate"]
