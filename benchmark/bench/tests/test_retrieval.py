from bench.retrieval import build_context, score, make_question, hits, DEPTHS

def test_build_places_all_needles_in_order():
    ctx, needles = build_context(2000, chars_per_token=4.0)
    assert len(needles) == len(DEPTHS)
    assert len(set(needles)) == len(needles)          # all unique
    positions = [ctx.find(n) for n in needles]
    assert all(p >= 0 for p in positions)             # all present
    assert positions == sorted(positions)             # placed by ascending depth

def test_score_is_fraction_found():
    _, needles = build_context(2000, 4.0)
    assert score(" ".join(needles), needles) == 1.0
    assert score(needles[0], needles) == 1.0 / len(needles)
    assert score("nothing here", needles) == 0.0

def test_question_mentions_count():
    _, needles = build_context(2000, 4.0)
    assert str(len(needles)) in make_question(needles)

def test_build_context_seeded_unique_needles():
    _, n0 = build_context(2000, 4.0, seed=0)
    _, n1 = build_context(2000, 4.0, seed=1)
    assert len(set(n0)) == len(n0)          # unique within a context
    assert n0 != n1                          # different seeds -> different needles


def test_build_context_deterministic():
    assert build_context(2000, 4.0, seed=7) == build_context(2000, 4.0, seed=7)


def test_build_context_needles_fixed_length():
    _, needles = build_context(2000, 4.0, seed=3)
    assert all(len(n) == 8 for n in needles)


def test_hits_per_needle():
    _, needles = build_context(2000, 4.0, seed=0)
    assert hits(", ".join(needles), needles) == [True] * len(needles)
    assert hits(needles[2], needles) == [i == 2 for i in range(len(needles))]
    assert hits("", needles) == [False] * len(needles)
    assert hits(None, needles) == [False] * len(needles)
