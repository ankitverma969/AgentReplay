from __future__ import annotations

from pathlib import Path

import pytest
from agentreplay.cli.main import build_parser, main


def test_help_contains_phase_one_commands() -> None:
    help_text = build_parser().format_help()

    assert "list" in help_text
    assert "record" in help_text
    assert "replay" in help_text
    assert "diff" in help_text
    assert "export" in help_text
    assert "security" in help_text


def test_help_exits_successfully() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0


def test_version_command_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["version"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.startswith("agentreplay ")


def test_list_command_is_successful(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["list", "--db-path", str(tmp_path / "empty.sqlite")])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "No recorded runs found." in captured.out
