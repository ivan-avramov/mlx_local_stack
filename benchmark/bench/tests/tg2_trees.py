"""Test/acceptance helper over the production materializer (`bench/tg2_materialize.py`)."""

from bench import structured_grade as sg  # noqa: F401  (re-exported for the acceptance script)
from bench import tg2_materialize as mat


def solutions(corpus, lang, slug):
    return mat.read_plan(corpus, lang, slug).solutions


def stub_tree(corpus, lang, slug, dest):
    return mat.prepare_tree(corpus, lang, slug, dest).tree


def apply_reference(corpus, lang, slug, tree):
    return mat.apply_reference(corpus, mat.read_plan(corpus, lang, slug), tree)


def reference_tree(corpus, lang, slug, dest):
    return apply_reference(corpus, lang, slug, stub_tree(corpus, lang, slug, dest))
