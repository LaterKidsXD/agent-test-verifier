from atv.report import Finding, Severity, verdict, to_json, to_text

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
