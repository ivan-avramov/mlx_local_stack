"""Regression cases from saved Math500 answers; no generation required."""
import pytest
from bench.grade import _math_eq

@pytest.mark.parametrize('pred,gold', [
    (r'(2, \infty)', r'(2,\infty)'),
    (r'\dfrac{9}{256}', r'\frac{9}{256}'),
    (r'\frac{4}{3}', r'\frac43'),
    ('(-2, 1)', '(-2,1)'),
])
def test_extracted_math_expressions_are_parsed_as_math(pred, gold):
    assert _math_eq(pred, gold)

@pytest.mark.parametrize('pred,gold', [
    ('(-2,1)', '(1,-2)'),
    (r'[2,\infty)', r'(2,\infty)'),
    (r'\frac{4}{3}', r'\frac{3}{4}'),
    ('', ''),
    ('not an answer', 'another non-answer'),
])
def test_incorrect_or_empty_answers_do_not_pass(pred, gold):
    assert not _math_eq(pred, gold)
