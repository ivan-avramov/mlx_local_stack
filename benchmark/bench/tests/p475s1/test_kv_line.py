"""`bench.kv_line`: parse the worker's `KV cache resolved:` line and judge it against an arm (R2, R22; contract component 1)."""
import pytest

from .fakes import ARMS, kv_line


def L():
    import bench.kv_line as m
    return m


def problems(text, arm):
    m = L()
    return m.kv_line_problems(m.parse_kv_line(text), arm)


# ------------------------------------------------------------------------------------------- parsing
def test_parse_reads_python_literals():
    # class: exercises new behaviour
    p = L().parse_kv_line(kv_line("TQ4"))
    assert p["kv_bits"] == 4.0 and isinstance(p["kv_bits"], float)
    assert p["kv_quant_scheme"] == "turboquant"
    assert p["kv_group_size"] == 64 and p["quantized_kv_start"] == 0
    assert p["TQ_KV_QUANT_MODE"] == "mse"
    for k in ("kv_key_bits", "kv_value_bits", "kv_key_scheme", "kv_value_scheme"):
        assert p[k] is None


def test_parse_native_line_has_none_bits():
    # class: exercises new behaviour
    assert L().parse_kv_line(kv_line("N16"))["kv_bits"] is None


def test_parse_takes_the_last_line_of_a_string():
    # class: exercises new behaviour (R22: string form)
    text = "noise\n" + kv_line("TQ4") + "\nmore noise\n" + kv_line("AF8") + "\ntrailing\n"
    p = L().parse_kv_line(text)
    assert p["kv_bits"] == 8.0 and p["kv_quant_scheme"] == "uniform"


def test_parse_takes_the_last_line_of_a_list():
    # class: exercises new behaviour (R22: list-of-lines form, with and without newlines)
    lines = ["noise", kv_line("TQ4") + "\n", "x", kv_line("AF8"), "tail"]
    p = L().parse_kv_line(lines)
    assert p["kv_bits"] == 8.0


def test_string_and_list_forms_agree():
    # class: exercises new behaviour (R22)
    lines = ["a", kv_line("TQ8"), "b"]
    assert L().parse_kv_line(lines) == L().parse_kv_line("\n".join(lines))


@pytest.mark.parametrize("text", ["", "no such line here\nanother\n", []], ids=["empty", "noise", "empty_list"])
def test_parse_refuses_when_the_line_is_absent(text):
    # class: exercises new behaviour
    with pytest.raises((ValueError, LookupError)):
        L().parse_kv_line(text)


@pytest.mark.parametrize("bad", [
    "KV cache resolved: kv_bits=4.0",                                             # truncated: fields missing
    "KV cache resolved: kv_bits=<garbage> kv_key_bits=None kv_value_bits=None kv_key_scheme=None kv_value_scheme=None "
    "kv_quant_scheme='turboquant' kv_group_size=64 quantized_kv_start=0 TQ_KV_QUANT_MODE='mse'",
])
def test_parse_refuses_a_malformed_line(bad):
    # class: exercises new behaviour
    with pytest.raises((ValueError, LookupError)):
        L().parse_kv_line(bad)


def test_a_malformed_last_line_is_refused_not_skipped_for_an_older_good_one():
    # class: exercises new behaviour (the LAST line decides; an older valid line is stale evidence)
    with pytest.raises((ValueError, LookupError)):
        L().parse_kv_line(kv_line("TQ4") + "\nKV cache resolved: kv_bits=4.0\n")


# ------------------------------------------------------------------------------------------- expected / problems
@pytest.mark.parametrize("arm,bits,scheme", [("AF8", 8, "uniform"), ("TQ8", 8, "turboquant"), ("AF4", 4, "uniform"),
                                              ("TQ4", 4, "turboquant"), ("TQ4-OFF", 4, "turboquant")])
def test_expected_kv_names_the_arms_codec(arm, bits, scheme):
    # class: exercises new behaviour
    e = L().expected_kv(arm)
    assert e["kv_bits"] == bits and e["kv_quant_scheme"] == scheme


@pytest.mark.parametrize("arm", ARMS)
def test_every_arms_own_line_has_no_problems(arm):
    # class: exercises new behaviour
    assert problems(kv_line(arm), arm) == []


def test_problems_is_a_list_of_strings():
    # class: exercises new behaviour
    out = problems(kv_line("TQ4"), "AF8")
    assert out and all(isinstance(x, str) for x in out)


@pytest.mark.parametrize("bits", [None, 0, 0.0])
def test_native_arm_accepts_none_or_numeric_zero_bits(bits):
    # class: exercises new behaviour
    assert problems(kv_line("N16", bits=bits), "N16") == []


@pytest.mark.parametrize("scheme", ["uniform", "turboquant", "whatever"])
def test_native_arm_does_not_compare_the_scheme(scheme):
    # class: exercises new behaviour
    assert problems(kv_line("N16", scheme=scheme), "N16") == []


@pytest.mark.parametrize("bits", [4.0, 8.0, 16.0])
def test_native_arm_refuses_a_quantized_line(bits):
    # class: exercises new behaviour
    assert problems(kv_line("N16", bits=bits), "N16")


@pytest.mark.parametrize("arm,line_arm", [("AF8", "AF4"), ("TQ8", "TQ4"), ("AF4", "AF8"), ("TQ4", "TQ8")])
def test_wrong_bits_are_refused(arm, line_arm):
    # class: exercises new behaviour
    assert problems(kv_line(line_arm), arm)


@pytest.mark.parametrize("arm,other", [("AF8", "turboquant"), ("AF4", "turboquant"), ("TQ4", "uniform"), ("TQ8", "uniform"),
                                       ("TQ4-OFF", "uniform")])
def test_wrong_scheme_is_refused(arm, other):
    # class: exercises new behaviour
    assert problems(kv_line(arm, scheme=other), arm)


@pytest.mark.parametrize("bits", [8, 8.0])
def test_bits_compare_numerically_int_or_float(bits):
    # class: exercises new behaviour
    assert problems(kv_line("AF8", bits=bits), "AF8") == []


@pytest.mark.parametrize("field", ["kv_key_bits", "kv_value_bits", "kv_key_scheme", "kv_value_scheme"])
def test_any_split_field_set_is_refused_on_a_quantized_arm(field):
    # class: exercises new behaviour (R2: split key / value widths and schemes)
    val = "'uniform'" if field.endswith("scheme") else 4.0
    assert problems(kv_line("TQ4", extra={field: val}), "TQ4")


@pytest.mark.parametrize("group", [32, 128, None])
def test_group_size_other_than_64_is_refused(group):
    # class: exercises new behaviour (R2)
    assert problems(kv_line("TQ4", group=group), "TQ4")


@pytest.mark.parametrize("start,ok", [(0, True), (0.0, True), (1, False), (4096, False), (None, False), ("0", False)])
def test_quantized_kv_start_is_compared_numerically(start, ok):
    # class: reproduces a failure the contract fixes (R22: a string compare of `0` vs `0.0` would refuse a right line)
    assert (problems(kv_line("AF4", start=start), "AF4") == []) is ok


@pytest.mark.parametrize("arm", ["TQ8", "TQ4", "TQ4-OFF"])
@pytest.mark.parametrize("mode", ["prod", None, ""])
def test_turboquant_arms_need_mse_mode(arm, mode):
    # class: exercises new behaviour (R2: TurboQuant mode); the logged value is already lower-cased by the server
    assert problems(kv_line(arm, mode=mode), arm)
