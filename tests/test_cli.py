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
