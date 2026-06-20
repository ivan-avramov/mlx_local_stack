from bench.retrieval import build_context, score, make_question, DEPTHS

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
