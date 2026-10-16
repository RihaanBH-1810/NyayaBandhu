import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from akn_parser import cli


@pytest.mark.parametrize("value", ["-1", "-20", "1.5", "abc"])
def test_count_rejects_invalid_values(value, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--pdf", "unused.pdf", "--count", value])
    assert exc.value.code == 2
    assert "must be a non-negative integer" in capsys.readouterr().err


@pytest.mark.parametrize("count, expected", [(None, 3), ("0", 3), ("2", 2)])
def test_count_limits_batch(count, expected, monkeypatch, tmp_path):
    calls = []

    class Parser:
        def __init__(self, **kwargs):
            pass

        def parse(self, path):
            calls.append(path)
            return SimpleNamespace(
                xml=b"<act/>", pages=[], redactions=0,
                report=SimpleNamespace(ok=True, summary=lambda: "valid"),
            )

    pdfs = ["a.pdf", "b.pdf", "c.pdf"]
    monkeypatch.setattr(cli, "ActParser", Parser)
    monkeypatch.setattr(cli, "collect_pdfs", lambda *_: pdfs)
    argv = ["-t", "base_act", "--out", str(tmp_path), "--quiet"]
    if count is not None:
        argv.extend(["--count", count])
    assert cli.main(argv) == 0
    assert calls == pdfs[:expected]
    assert len(list(tmp_path.glob("*.xml"))) == expected


def test_quiet_help(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "Suppress progress, reports, and concise failure messages." in (
        " ".join(capsys.readouterr().out.split())
    )


@pytest.mark.parametrize("directory_exists", [False, True])
def test_missing_input(directory_exists, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "REPO_ROOT", str(tmp_path))
    if directory_exists:
        (tmp_path / "data" / "v0s").mkdir(parents=True)
    message = "No PDF files found" if directory_exists else "No data directory"
    with pytest.raises(cli.NoInputError, match=message):
        cli.collect_pdfs("base_act", None)
    assert cli.main(["-t", "base_act", "--quiet"]) == 1
    captured = capsys.readouterr()
    assert message in captured.err
    assert "Traceback" not in captured.err
    assert not (tmp_path / "out").exists()


def test_collect_pdfs_sorts_and_filters(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "REPO_ROOT", str(tmp_path))
    root = tmp_path / "data" / "v0s"
    for name in ["eng/z.pdf", "eng/a.pdf", "eng/notes.txt", "kan/b.pdf"]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    assert cli.collect_pdfs("base_act", None) == sorted(
        str(root / name) for name in ["eng/z.pdf", "eng/a.pdf", "kan/b.pdf"]
    )
    assert cli.collect_pdfs("base_act", "eng") == [
        str(root / "eng/a.pdf"), str(root / "eng/z.pdf"),
    ]
    with pytest.raises(cli.NoInputError):
        cli.collect_pdfs("base_act", "missing")


@pytest.mark.parametrize("show_traceback", [False, True])
@pytest.mark.parametrize("quiet", [False, True])
@pytest.mark.parametrize("strict", [False, True])
def test_processing_failure(show_traceback, quiet, strict, monkeypatch,
                            tmp_path, capsys):
    calls = []

    class Parser:
        def __init__(self, **kwargs):
            pass

        def parse(self, path):
            calls.append(path)
            raise ValueError("broken document")

    monkeypatch.setattr(cli, "ActParser", Parser)
    monkeypatch.setattr(cli, "collect_pdfs", lambda *_: ["a.pdf", "b.pdf"])
    argv = ["-t", "base_act", "--out", str(tmp_path)]
    argv += [flag for enabled, flag in [
        (show_traceback, "--traceback"), (quiet, "--quiet"), (strict, "--strict"),
    ] if enabled]
    assert cli.main(argv) == int(strict)
    assert calls == ["a.pdf", "b.pdf"]
    captured = capsys.readouterr()
    assert ("FAILED: ValueError: broken document" in captured.out) == (not quiet)
    assert ("Traceback (most recent call last):" in captured.err) == show_traceback
    if show_traceback:
        assert "raise ValueError" in captured.err
        assert captured.err.count("ValueError: broken document") == 2


@pytest.mark.parametrize("entry_point", ["console", "module", "script"])
def test_installed_entry_points(entry_point, tmp_path):
    root = Path(__file__).resolve().parents[1]
    commands = {
        "console": [str(Path(sys.executable).with_name("akn-parser"))],
        "module": [sys.executable, "-m", "akn_parser.cli"],
        "script": [sys.executable, str(root / "scripts" / "akn-parser.py")],
    }
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [*commands[entry_point], "--help"], cwd=tmp_path, env=env,
        capture_output=True, text=True, check=True,
    )
    assert "--traceback" in result.stdout
    assert "--quiet" in result.stdout
