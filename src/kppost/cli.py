from __future__ import annotations

import json
from pathlib import Path

import click

from .canva import export_canva_assets, import_canva_assets
from .config import load_config
from .errors import KppostError, ValidationError
from .importer import Importer, resolve_post_taxonomies
from .manifest import generate_manifest, validate_batch
from .prepare import default_output_root, prepare_content
from .wordpress import WordPressClient


def _client(batch_root: Path) -> WordPressClient:
    config = load_config(batch_root)
    return WordPressClient(
        base_url=config.wp_url,
        username=config.wp_username,
        application_password=config.wp_application_password,
        timeout=config.timeout_seconds,
        verify_ssl=config.verify_ssl,
    )


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, ValidationError):
        for message in exc.messages:
            click.echo(f"ERROR: {message}", err=True)
    else:
        click.echo(f"ERROR: {exc}", err=True)
    raise click.exceptions.Exit(1)


@click.group()
@click.version_option()
def cli() -> None:
    """Generate and post Markdown batches into WordPress.

    \b
    Workflow:
    1. kppost prepare <source> [output]
    2. Review Markdown, images, and departments.json
    3. Optional: kppost canva export <batch> <output>
    4. Optional: kppost canva import <batch> -f <feature.zip> -nw <news.zip>
    5. kppost generate <batch>
    6. kppost validate <batch>
    7. kppost preflight <batch>
    8. kppost post <batch>  (alias: kppost import <batch>)
    """


@cli.command()
@click.argument(
    "source_directory",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
)
@click.argument(
    "output_directory",
    type=click.Path(path_type=Path, file_okay=False),
    required=False,
)
@click.option(
    "--department-code",
    default="inv",
    show_default=True,
    help="Department code used in generated Markdown filenames.",
)
def prepare(
    source_directory: Path,
    output_directory: Path | None,
    department_code: str,
) -> None:
    """Prepare raw content. Next: review files, then generate."""
    try:
        if output_directory is None:
            output_directory = default_output_root(source_directory)
        report = prepare_content(
            source_directory,
            output_directory,
            department_code=department_code,
        )
    except KppostError as exc:
        _handle_error(exc)
        return
    click.echo(
        f"Prepared {report['prepared']} post(s), "
        f"skipped {len(report['skipped'])}: {output_directory}"
    )
    for skipped in report["skipped"]:
        click.echo(
            f"SKIPPED: {skipped['source_folder']} ({skipped['reason']})"
        )
    click.echo(f"Report: {output_directory / 'prepare-report.json'}")
    click.echo(f"Department template: {report['departments_file']}")


@cli.group()
def canva() -> None:
    """Optional Canva export/import between prepare and generate."""


@canva.command(name="export")
@click.argument(
    "batch_directory",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
)
@click.argument(
    "output_directory",
    type=click.Path(path_type=Path, file_okay=False),
)
def canva_export(batch_directory: Path, output_directory: Path) -> None:
    """Create Canva Sheet XLSX files. Next: Canva import."""
    try:
        result = export_canva_assets(batch_directory, output_directory)
    except KppostError as exc:
        _handle_error(exc)
        return
    click.echo(f"Exported {result['posts']} post(s): {output_directory}")
    click.echo(f"Feature workbook: {result['feature_workbook']}")
    click.echo(f"News workbook: {result['news_workbook']}")


@canva.command(name="import")
@click.argument(
    "batch_directory",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
)
@click.option(
    "-f",
    "--feature",
    "feature_zip",
    required=True,
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    help="ZIP downloaded from the Feature Image Canva design.",
)
@click.option(
    "-nw",
    "--news-watermark",
    "news_zip",
    required=True,
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    help="ZIP downloaded from the News Watermark Canva design.",
)
def canva_import(
    batch_directory: Path,
    feature_zip: Path,
    news_zip: Path,
) -> None:
    """Replace batch images from Canva ZIP files. Next: generate."""
    try:
        result = import_canva_assets(batch_directory, feature_zip, news_zip)
    except KppostError as exc:
        _handle_error(exc)
        return
    click.echo(f"Imported Canva images for {len(result['posts'])} post(s)")
    click.echo(f"Report: {result['report_path']}")


@cli.command()
@click.argument(
    "batch_directory",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
)
@click.option("--force", is_flag=True, help="Overwrite an existing batch.json.")
def generate(batch_directory: Path, force: bool) -> None:
    """Generate batch.json. Next: validate."""
    try:
        destination, manifest = generate_manifest(batch_directory, force=force)
    except KppostError as exc:
        _handle_error(exc)
        return
    click.echo(f"Generated {len(manifest['posts'])} post(s): {destination}")
    if destination.name == "generated-preview.json":
        click.echo("batch.json was not changed; review the generated preview.")


@cli.command(name="validate")
@click.argument(
    "batch_directory",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
)
def validate_command(batch_directory: Path) -> None:
    """Validate a generated batch locally. Next: preflight."""
    try:
        manifest = validate_batch(batch_directory)
    except KppostError as exc:
        _handle_error(exc)
        return
    click.echo(f"Valid batch: {manifest['batch_id']} ({len(manifest['posts'])} posts)")


@cli.command()
@click.argument(
    "batch_directory",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
)
def preflight(batch_directory: Path) -> None:
    """Check WordPress read-only. Next: post."""
    try:
        manifest = validate_batch(batch_directory)
        client = _client(batch_directory)
        result = client.preflight()
        for post in manifest["posts"]:
            resolve_post_taxonomies(client, post)
        result["taxonomy_posts_checked"] = len(manifest["posts"])
    except KppostError as exc:
        _handle_error(exc)
        return
    click.echo(f"Valid batch: {manifest['batch_id']}")
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))


def _post_batch(batch_directory: Path) -> None:
    try:
        report = Importer(
            batch_directory,
            _client(batch_directory),
            progress=click.echo,
        ).run()
    except KppostError as exc:
        _handle_error(exc)
        return
    summary = report["summary"]
    click.echo(
        "Post complete: "
        f"{summary['success']} success, "
        f"{summary['skipped']} skipped, "
        f"{summary['failed']} failed"
    )
    click.echo(f"Report: {report['report_path']}")
    if summary["failed"]:
        raise click.exceptions.Exit(1)


@cli.command(name="post")
@click.argument(
    "batch_directory",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
)
def post_command(batch_directory: Path) -> None:
    """Validate, upload media, and create WordPress posts."""
    _post_batch(batch_directory)


@cli.command(name="import")
@click.argument(
    "batch_directory",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
)
def import_command(batch_directory: Path) -> None:
    """Alias for post. Prefer: kppost post <batch>."""
    _post_batch(batch_directory)


if __name__ == "__main__":
    cli()
