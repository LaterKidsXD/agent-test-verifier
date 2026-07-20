from atv.report import (
    Finding,
    Severity,
    verdict,
    to_json,
    to_text,
    to_github,
    to_markdown,
)

def _f():
    return [Finding("t/test_x.py", 12, "null_test", Severity.HIGH, "asserts nothing", "def test_x")]

def test_verdict_flags_when_findings_present():
    assert verdict(_f()) == "flagged"
    assert verdict([]) == "clean"

def test_to_json_shape_is_stable():
    out = to_json(_f(), {"files_analyzed": 1, "skipped_unparseable": 0, "counts_by_pattern": {"null_test": 1}})
    assert out["verdict"] == "flagged"
    assert out["findings"][0] == {
        "file": "t/test_x.py", "line": 12, "pattern": "null_test",
        "severity": "high", "message": "asserts nothing", "snippet": "def test_x"}
    assert out["summary"]["counts_by_pattern"] == {"null_test": 1}

def test_to_text_clean_and_flagged():
    assert "clean" in to_text([], {"files_analyzed": 2, "skipped_unparseable": 0, "counts_by_pattern": {}})
    txt = to_text(_f(), {"files_analyzed": 1, "skipped_unparseable": 0, "counts_by_pattern": {"null_test": 1}})
    assert "FLAGGED" in txt and "test_x.py:12" in txt and "high" in txt


def test_to_github_annotation_shape():
    fs = [Finding("t/test_x.py", 12, "null_test", Severity.HIGH, "asserts nothing")]
    out = to_github(fs, fail_on=Severity.LOW)
    assert out == (
        "::error file=t/test_x.py,line=12,title=atv%3A null_test::asserts nothing")


def test_to_github_error_at_or_above_threshold_warning_below():
    fs = [
        Finding("a.py", 1, "force_pass_hook", Severity.HIGH, "m1"),
        Finding("b.py", 2, "test_skipped", Severity.LOW, "m2"),
    ]
    lines = to_github(fs, fail_on=Severity.MEDIUM).splitlines()
    assert lines[0].startswith("::error ")
    assert lines[1].startswith("::warning ")


def test_to_github_threshold_equal_severity_is_error():
    fs = [Finding("a.py", 1, "p", Severity.MEDIUM, "m")]
    assert to_github(fs, fail_on=Severity.MEDIUM).startswith("::error ")


def test_to_github_escapes_message_and_properties():
    fs = [Finding("dir:a,b/f.py", 3, "p", Severity.HIGH, "100% bad\r\nnext: x,y")]
    out = to_github(fs, fail_on=Severity.LOW)
    # property channel: %, \r, \n AND : , are escaped
    assert "file=dir%3Aa%2Cb/f.py" in out
    # message channel: %, \r, \n escaped but : and , stay literal
    assert out.endswith("::100%25 bad%0D%0Anext: x,y")


def test_to_github_line_zero_is_file_level():
    fs = [Finding("t/test_x.py", 0, "assertion_removed", Severity.MEDIUM, "gone")]
    out = to_github(fs, fail_on=Severity.LOW)
    assert "line=" not in out
    assert "file=t/test_x.py,title=" in out


def test_to_github_empty_findings_is_empty():
    assert to_github([], fail_on=Severity.LOW) == ""


def test_to_markdown_flagged_table():
    fs = [
        Finding("tests/conftest.py", 3, "force_pass", Severity.HIGH,
                "hook overrides outcome"),
        Finding("tests/test_x.py", 12, "null_test", Severity.LOW,
                "no meaningful assertion"),
    ]
    summary = {"files_analyzed": 3, "skipped_unparseable": 0,
               "counts_by_pattern": {"force_pass": 1, "null_test": 1}}
    out = to_markdown(fs, summary)
    assert "### agent-test-verifier — FLAGGED (2 finding(s))" in out
    assert "3 file(s) analyzed · counts: `force_pass` 1, `null_test` 1" in out
    assert "| Severity | File | Line | Pattern | Message |" in out
    assert "|---|---|---|---|---|" in out
    assert ("| high | tests/conftest.py | 3 | force_pass "
            "| hook overrides outcome |") in out
    assert ("| low | tests/test_x.py | 12 | null_test "
            "| no meaningful assertion |") in out


def test_to_markdown_escapes_cells():
    fs = [Finding("a.py", 1, "p", Severity.HIGH, "bad | pipe\nand newline")]
    summary = {"files_analyzed": 1, "skipped_unparseable": 0,
               "counts_by_pattern": {"p": 1}}
    assert "bad \\| pipe and newline" in to_markdown(fs, summary)


def test_to_markdown_clean():
    summary = {"files_analyzed": 3, "skipped_unparseable": 0,
               "counts_by_pattern": {}}
    out = to_markdown([], summary)
    assert "### agent-test-verifier — clean" in out
    assert "3 file(s) analyzed, no faked-green patterns found." in out
