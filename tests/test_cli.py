from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

import kppost.cli
from kppost.cli import cli


def test_prepare_uses_default_output_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "69-04-txt-gen"
    source.mkdir()
    calls: list[tuple[Path, Path, str]] = []

    def fake_prepare_content(
        source_directory: Path,
        output_directory: Path,
        department_code: str,
    ) -> dict[str, object]:
        calls.append((source_directory, output_directory, department_code))
        return {
            "prepared": 0,
            "skipped": [],
            "departments_file": str(output_directory / "departments.json"),
        }

    monkeypatch.setattr(kppost.cli, "prepare_content", fake_prepare_content)

    result = CliRunner().invoke(cli, ["prepare", str(source)])

    assert result.exit_code == 0
    assert calls == [(source, tmp_path / "batch-69-04", "inv")]
    assert f"Prepared 0 post(s), skipped 0: {tmp_path / 'batch-69-04'}" in result.output


def test_prepare_keeps_explicit_output_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "69-04"
    source.mkdir()
    output = tmp_path / "custom-ready"
    calls: list[tuple[Path, Path, str]] = []

    def fake_prepare_content(
        source_directory: Path,
        output_directory: Path,
        department_code: str,
    ) -> dict[str, object]:
        calls.append((source_directory, output_directory, department_code))
        return {
            "prepared": 0,
            "skipped": [],
            "departments_file": str(output_directory / "departments.json"),
        }

    monkeypatch.setattr(kppost.cli, "prepare_content", fake_prepare_content)

    result = CliRunner().invoke(cli, ["prepare", str(source), str(output)])

    assert result.exit_code == 0
    assert calls == [(source, output, "inv")]
