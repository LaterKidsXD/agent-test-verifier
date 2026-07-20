import json

from atv.cli import main

def test_diff_mode_flags_benchjack(capsys):
    rc = main(["--diff", "tests/fixtures/benchjack_conftest.diff", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["verdict"] == "flagged"
    assert out["findings"][0]["pattern"] == "force_pass_hook"

def test_clean_diff_returns_zero(tmp_path, capsys):
    p = tmp_path / "clean.diff"
    p.write_text(
        "diff --git a/tests/test_a.py b/tests/test_a.py\n"
        "new file mode 100644\n--- /dev/null\n+++ b/tests/test_a.py\n"
        "@@ -0,0 +1,2 @@\n+def test_a():\n+    assert 1 + 1 == 2\n"
    )
    rc = main(["--diff", str(p)])
    assert rc == 0
    assert "clean" in capsys.readouterr().out

def test_missing_args_is_usage_error():
    try:
        main([])
    except SystemExit as e:  # argparse .error() raises SystemExit(2)
        assert e.code == 2
    else:
        raise AssertionError("expected SystemExit(2)")

def test_repo_mode_git_failure_returns_2(tmp_path, capsys):
    # tmp_path is not a git repo -> git diff fails -> exit 2 (NOT a false clean/0)
    rc = main(["--repo", str(tmp_path), "--base", "HEAD"])
    assert rc == 2
    assert "git" in capsys.readouterr().err.lower()

def test_diff_missing_file_returns_2(tmp_path, capsys):
    rc = main(["--diff", str(tmp_path / "nope.diff")])
    assert rc == 2
    assert "cannot read" in capsys.readouterr().err.lower()

def test_malformed_diff_returns_2(tmp_path, capsys):
    p = tmp_path / "malformed.diff"
    p.write_text("+added without a header\n-removed without a header\n")
    rc = main(["--diff", str(p)])
    assert rc == 2
    assert "malformed" in capsys.readouterr().err.lower()

def test_unparseable_file_surfaces_warning(tmp_path, capsys):
    p = tmp_path / "broken.diff"
    p.write_text(
        "diff --git a/tests/test_broken.py b/tests/test_broken.py\n"
        "new file mode 100644\n--- /dev/null\n+++ b/tests/test_broken.py\n"
        "@@ -0,0 +1,1 @@\n+def test_x(:\n"
    )
    main(["--diff", str(p)])
    err = capsys.readouterr().err
    assert "warning" in err
    assert "test_broken.py" in err

def test_format_github_emits_error_annotation(capsys):
    rc = main(["--diff", "tests/fixtures/benchjack_conftest.diff",
               "--format", "github"])
    out = capsys.readouterr().out
    assert rc == 1
    assert out.startswith("::error ")
    assert "file=conftest.py" in out
    assert "title=atv%3A force_pass_hook" in out


def test_format_github_clean_diff_prints_nothing(tmp_path, capsys):
    p = tmp_path / "clean.diff"
    p.write_text(
        "diff --git a/tests/test_a.py b/tests/test_a.py\n"
        "new file mode 100644\n--- /dev/null\n+++ b/tests/test_a.py\n"
        "@@ -0,0 +1,2 @@\n+def test_a():\n+    assert 1 + 1 == 2\n"
    )
    rc = main(["--diff", str(p), "--format", "github"])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_format_github_below_threshold_warns_and_passes(tmp_path, capsys):
    # test_skipped is MEDIUM; with --fail-on high it must warn, not fail
    p = tmp_path / "skip.diff"
    p.write_text(
        "diff --git a/tests/test_s.py b/tests/test_s.py\n"
        "new file mode 100644\n--- /dev/null\n+++ b/tests/test_s.py\n"
        "@@ -0,0 +1,3 @@\n+@pytest.mark.skip\n+def test_s():\n"
        "+    assert 1 + 1 == 2\n"
    )
    rc = main(["--diff", str(p), "--format", "github", "--fail-on", "high"])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("::warning ")
    assert "test_skipped" in out


def test_format_markdown_flagged(capsys):
    rc = main(["--diff", "tests/fixtures/benchjack_conftest.diff",
               "--format", "markdown"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "### agent-test-verifier — FLAGGED" in out
    assert "| high | conftest.py | 1 | force_pass_hook |" in out


def test_json_flag_is_alias_for_format_json(capsys):
    rc1 = main(["--diff", "tests/fixtures/benchjack_conftest.diff", "--json"])
    out1 = capsys.readouterr().out
    rc2 = main(["--diff", "tests/fixtures/benchjack_conftest.diff",
                "--format", "json"])
    out2 = capsys.readouterr().out
    assert (rc1, out1) == (rc2, out2)


def test_invalid_format_is_usage_error():
    try:
        main(["--diff", "tests/fixtures/benchjack_conftest.diff",
              "--format", "yaml"])
    except SystemExit as e:
        assert e.code == 2
    else:
        raise AssertionError("expected SystemExit(2)")
