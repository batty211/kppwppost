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


def test_prepare_uses_generic_default_output_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "posts"
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
    assert calls == [(source, tmp_path / "batch-posts", "inv")]


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


def test_root_help_shows_numbered_workflow() -> None:
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "1. kppost prepare <source> [output]" in result.output
    assert "1. kppost prepare <source> [output]\n  2. Review" in result.output
    assert "3. Optional: kppost canva export <batch> <output>" in result.output
    assert "8. kppost post <batch>  (alias: kppost import <batch>)" in result.output


def test_post_and_import_commands_use_same_post_runner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    batch = tmp_path / "batch"
    batch.mkdir()
    calls: list[Path] = []

    class FakeImporter:
        def __init__(self, batch_directory, client, progress) -> None:
            calls.append(batch_directory)

        def run(self):
            return {
                "summary": {"success": 1, "skipped": 0, "failed": 0},
                "report_path": "report.json",
            }

    monkeypatch.setattr(kppost.cli, "Importer", FakeImporter)
    monkeypatch.setattr(kppost.cli, "_client", lambda batch_directory: object())

    post_result = CliRunner().invoke(cli, ["post", str(batch)])
    import_result = CliRunner().invoke(cli, ["import", str(batch)])

    assert post_result.exit_code == 0
    assert import_result.exit_code == 0
    assert calls == [batch, batch]
    assert "Post complete: 1 success, 0 skipped, 0 failed" in post_result.output
    assert "Post complete: 1 success, 0 skipped, 0 failed" in import_result.output
