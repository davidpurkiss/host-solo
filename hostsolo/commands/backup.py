"""Backup management commands."""

from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from hostsolo.config import get_project_root, load_config, load_env_settings

app = typer.Typer()
console = Console()


def get_backup_provider():
    """Get the configured backup provider."""
    from hostsolo.providers.backup import S3BackupProvider

    config = load_config()
    settings = load_env_settings()

    if config.backup.provider == "s3":
        if not settings.aws_access_key_id or not settings.aws_secret_access_key:
            console.print("[red]✗[/red] S3 credentials not configured")
            console.print("  Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
            raise typer.Exit(1)
        return S3BackupProvider(
            bucket=config.backup.bucket,
            access_key=settings.aws_access_key_id,
            secret_key=settings.aws_secret_access_key,
            region=settings.aws_region,
            endpoint_url=config.backup.endpoint_url,
        )
    else:
        console.print(f"[red]✗[/red] Unknown backup provider: {config.backup.provider}")
        raise typer.Exit(1)


def get_backup_paths(app_name: str, env_name: str) -> list[Path]:
    """Get the paths to backup for an app."""
    config = load_config()
    project_root = get_project_root()

    if app_name not in config.apps:
        console.print(f"[red]✗[/red] App '{app_name}' not found in configuration")
        raise typer.Exit(1)

    app_config = config.apps[app_name]
    paths = []

    for path_template in app_config.backup_paths:
        # Replace ${ENV} with the environment name
        path_str = path_template.replace("${ENV}", env_name)
        full_path = project_root / path_str
        if full_path.exists():
            paths.append(full_path)
        else:
            console.print(f"[yellow]![/yellow] Backup path does not exist: {full_path}")

    return paths


@app.command()
def now(
    app_name: str = typer.Argument(..., help="Name of the app to backup"),
    env_name: str = typer.Option("prod", "--env", "-e", help="Target environment"),
) -> None:
    """Create an immediate backup."""
    provider = get_backup_provider()
    paths = get_backup_paths(app_name, env_name)

    if not paths:
        console.print(f"[yellow]![/yellow] No backup paths configured for {app_name}")
        raise typer.Exit(1)

    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
    console.print(f"[bold]Creating backup for {app_name} ({env_name})...[/bold]")
    console.print(f"  Timestamp: {timestamp}")

    for path in paths:
        console.print(f"  Backing up: {path}")

        try:
            backup_key = f"{env_name}/{app_name}/{timestamp}/{path.name}"
            provider.upload_directory(path, backup_key)
            console.print(f"[green]✓[/green] Uploaded: {backup_key}")
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to backup {path}: {e}")
            raise typer.Exit(1)

    console.print(f"[green]✓[/green] Backup complete")


@app.command("list")
def list_backups(
    app_name: str = typer.Argument(..., help="Name of the app"),
    env_name: str = typer.Option("prod", "--env", "-e", help="Target environment"),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum number of backups to show"),
) -> None:
    """List available backups."""
    provider = get_backup_provider()

    prefix = f"{env_name}/{app_name}/"
    console.print(f"[bold]Backups for {app_name} ({env_name})[/bold]")

    try:
        backups = provider.list_backups(prefix)

        # Group by timestamp
        timestamps: dict[str, list[str]] = {}
        for backup in backups:
            parts = backup.split("/")
            if len(parts) >= 3:
                ts = parts[2]  # env/app/timestamp/...
                if ts not in timestamps:
                    timestamps[ts] = []
                timestamps[ts].append(backup)

        if not timestamps:
            console.print("  No backups found")
            return

        table = Table()
        table.add_column("Timestamp")
        table.add_column("Files")

        for ts in sorted(timestamps.keys(), reverse=True)[:limit]:
            table.add_row(ts, str(len(timestamps[ts])))

        console.print(table)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to list backups: {e}")
        raise typer.Exit(1)


@app.command()
def restore(
    app_name: str = typer.Argument(..., help="Name of the app to restore"),
    env_name: str = typer.Option("prod", "--env", "-e", help="Target environment"),
    timestamp: str = typer.Option(..., "--timestamp", "-t", help="Backup timestamp to restore"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Restore from a backup."""
    provider = get_backup_provider()
    paths = get_backup_paths(app_name, env_name)

    if not paths:
        console.print(f"[yellow]![/yellow] No backup paths configured for {app_name}")
        raise typer.Exit(1)

    if not force:
        console.print(f"[yellow]Warning:[/yellow] This will overwrite existing data in:")
        for path in paths:
            console.print(f"  {path}")
        confirm = typer.confirm("Continue?")
        if not confirm:
            raise typer.Abort()

    console.print(f"[bold]Restoring {app_name} ({env_name}) from {timestamp}...[/bold]")

    for path in paths:
        backup_key = f"{env_name}/{app_name}/{timestamp}/{path.name}"
        console.print(f"  Restoring: {backup_key} → {path}")

        try:
            provider.download_directory(backup_key, path)
            console.print(f"[green]✓[/green] Restored: {path}")
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to restore {path}: {e}")
            raise typer.Exit(1)

    console.print(f"[green]✓[/green] Restore complete")
    console.print()
    console.print("[yellow]Note:[/yellow] You may need to restart the app: hostsolo deploy restart")


@app.command()
def delete(
    app_name: str = typer.Argument(..., help="Name of the app"),
    env_name: str = typer.Option("prod", "--env", "-e", help="Target environment"),
    timestamp: str = typer.Option(..., "--timestamp", "-t", help="Backup timestamp to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete a backup."""
    provider = get_backup_provider()

    backup_prefix = f"{env_name}/{app_name}/{timestamp}/"

    if not force:
        confirm = typer.confirm(f"Delete backup {timestamp} for {app_name} ({env_name})?")
        if not confirm:
            raise typer.Abort()

    console.print(f"[bold]Deleting backup {timestamp}...[/bold]")

    try:
        provider.delete_backup(backup_prefix)
        console.print(f"[green]✓[/green] Backup deleted")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to delete backup: {e}")
        raise typer.Exit(1)
