"""P604: a Go package-load error the model's own tree causes is a scored build failure, never an infrastructure abort.

Live trigger (Wave 2b leg 5 `tg1-p426-on-s2.a1`, `go/book-store`, an intermediate grade): the model left a scratch `brute_verify.go`
(`package main`) beside its solution; `go test -json` emitted no JSON events and stderr held exactly the line below, rc 1 →
`TransportAbort("Go report has no test events or build error")` → a systemic stop. 1 of 349 stored Go grades."""
import pytest

from bench import structured_grade as sg

REAL = "found packages bookstore (book_store.go) and main (brute_verify.go) in /work\n"


def test_the_real_package_load_error_is_a_scored_build_failure_P604():
    r = sg.parse_go("", 1, stderr=REAL)
    assert r.passing == set() and r.collected == set()


@pytest.mark.parametrize("err", [
    "/work/x.go:1:1: expected 'package', found 'EOF'\n",
    "x.go:1:9: expected 'IDENT', found 'EOF'\n",                                # review r1: a bare `package` clause
    "./book_store.go:3:8: package github.com/foo/bar is not in std (/usr/local/go/src/github.com/foo/bar)\n",
    "book_store.go:3:8: no required module provides package github.com/foo/bar; to add it:\n",
    "package bookstore\n\timports bookstore: import cycle not allowed\n",
])
def test_other_model_caused_load_errors_are_scored_P604(err):
    assert sg.parse_go("", 1, stderr=err).passing == set()


@pytest.mark.parametrize("rc, err", [
    (1, ""), (1, "something unexpected\n"), (2, ""),
    (1, "no Go files in /work\n"),                                                # review r1: an empty / stale mount
    (1, "go: go.mod file not found in current directory or any parent directory; see 'go help modules'\n"),
    (1, "go: errors parsing go.mod:\n/work/go.mod:3: unknown directive: bogus\n"),   # go.mod is protected (tampered)
    (1, "book_store_test.go:1:1: expected 'package', found 'EOF'\n"),             # the tests are protected
    (1, "found packages a (a.go) and b (b.go) in /elsewhere\n"),
    (1, "found packages a (a.go) and b (b.go) in /work-old\n"),                    # review r2: exactly /work
    (0, REAL),
])
def test_an_unexplained_or_unattributable_report_still_aborts_P604(rc, err):
    with pytest.raises(sg.TransportAbort, match="no test events or build error"):
        sg.parse_go("", rc, stderr=err)


def test_docker_failures_still_abort_first_P604():
    with pytest.raises(sg.TransportAbort, match="Docker infrastructure"):
        sg.parse_go("", 1, stderr="Cannot connect to the Docker daemon\n" + REAL)


def test_the_grader_version_records_the_change_P604():
    assert sg.VERSION != "m62-structured-v2"
