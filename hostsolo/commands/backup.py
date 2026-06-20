"""Backup management commands."""

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from hostsolo.config import get_project_root, load_config, load_env_settings

app = typer.Typer()
console = Console()

schedule_app = typer.Typer(help="Manage the automated backup schedule (systemd user timer)")
app.add_typer(schedule_app, name="schedule")

# systemd user unit names for the scheduled backup.
SERVICE_NAME = "hostsolo-backup.service"
TIMER_NAME = "hostsolo-backup.timer"


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


def _backup_app(provider, app_name: str, env_name: str, timestamp: str) -> int:
    """Back up a single app's configured paths. Returns the number of paths uploaded."""
    paths = get_backup_paths(app_name, env_name)

    if not paths:
        console.print(f"[yellow]![/yellow] No backup paths configured for {app_name}")
        return 0

    for path in paths:
        console.print(f"  Backing up: {path}")

        try:
            backup_key = f"{env_name}/{app_name}/{timestamp}/{path.name}"
            provider.upload_directory(path, backup_key)
            console.print(f"[green]✓[/green] Uploaded: {backup_key}")
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to backup {path}: {e}")
            raise typer.Exit(1)

    return len(paths)


@app.command()
def now(
    app_name: str = typer.Argument(..., help="Name of the app to backup"),
    env_name: str = typer.Option("prod", "--env", "-e", help="Target environment"),
) -> None:
    """Create an immediate backup."""
    provider = get_backup_provider()

    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
    console.print(f"[bold]Creating backup for {app_name} ({env_name})...[/bold]")
    console.print(f"  Timestamp: {timestamp}")

    uploaded = _backup_app(provider, app_name, env_name, timestamp)
    if uploaded == 0:
        raise typer.Exit(1)

    console.print(f"[green]✓[/green] Backup complete")


@app.command("all")
def backup_all(
    env_name: str = typer.Option("prod", "--env", "-e", help="Target environment"),
) -> None:
    """Back up every app that has backup paths configured.

    This is the entrypoint used by the scheduled backup timer.
    """
    config = load_config()
    provider = get_backup_provider()

    apps_to_backup = [
        name for name, app_config in config.apps.items() if app_config.backup_paths
    ]

    if not apps_to_backup:
        console.print("[yellow]![/yellow] No apps have backup paths configured")
        raise typer.Exit(1)

    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
    console.print(
        f"[bold]Backing up {len(apps_to_backup)} app(s) for {env_name}...[/bold]"
    )
    console.print(f"  Timestamp: {timestamp}")

    failures = 0
    for app_name in apps_to_backup:
        console.print(f"[bold]{app_name}[/bold]")
        try:
            _backup_app(provider, app_name, env_name, timestamp)
        except typer.Exit:
            # _backup_app already printed the error; keep going so one bad app
            # doesn't block backups for the others.
            failures += 1

    if failures:
        console.print(f"[red]✗[/red] {failures} app(s) failed to back up")
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
    console.print(f"[yellow]Note:[/yellow] You may need to restart the app: hostsolo deploy restart {app_name} --env {env_name}")


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


def _systemd_user_dir() -> Path:
    """Directory for systemd user units (~/.config/systemd/user)."""
    return Path.home() / ".config" / "systemd" / "user"


def _hostsolo_bin() -> str:
    """Command used by the systemd service to run hostsolo.

    Prefer the console script that lives next to the running interpreter so the
    timer always uses *this* install (a bare `which hostsolo` can resolve to a
    stale system-wide path). Fall back to PATH, then to running the module via
    the current interpreter.
    """
    # Note: do NOT resolve() sys.executable — in a venv it's a symlink to the
    # system interpreter, and following it would point us outside the venv.
    candidate = Path(sys.executable).parent / "hostsolo"
    if candidate.exists():
        return str(candidate)
    found = shutil.which("hostsolo")
    if found:
        return str(Path(found).resolve())
    return f"{sys.executable} -m hostsolo.cli"


def _run_systemctl(*args: str) -> subprocess.CompletedProcess:
    """Run `systemctl --user ...`, raising a clear error if systemd is absent."""
    try:
        return subprocess.run(
            ["systemctl", "--user", *args],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        console.print("[red]✗[/red] systemctl not found — a systemd-based Linux host is required")
        raise typer.Exit(1)


@schedule_app.command("install")
def schedule_install(
    env_name: str = typer.Option("prod", "--env", "-e", help="Environment to back up on schedule"),
) -> None:
    """Install (or update) the systemd user timer that runs scheduled backups."""
    from hostsolo.scheduler import (
        cron_to_oncalendar,
        render_service_unit,
        render_timer_unit,
    )

    config = load_config()
    schedule = config.backup.schedule

    try:
        oncalendar = cron_to_oncalendar(schedule)
    except ValueError as e:
        console.print(f"[red]✗[/red] Could not convert backup schedule '{schedule}': {e}")
        console.print("  Set backup.schedule in hostsolo.yaml to a supported cron expression.")
        raise typer.Exit(1)

    unit_dir = _systemd_user_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)

    service_path = unit_dir / SERVICE_NAME
    timer_path = unit_dir / TIMER_NAME

    service_path.write_text(
        render_service_unit(_hostsolo_bin(), get_project_root(), env_name)
    )
    timer_path.write_text(render_timer_unit(oncalendar, env_name))

    console.print(f"[bold]Installing scheduled backups for {env_name}...[/bold]")
    console.print(f"  Schedule: {schedule}  →  OnCalendar={oncalendar}")

    reload_result = _run_systemctl("daemon-reload")
    if reload_result.returncode != 0:
        console.print(f"[red]✗[/red] systemctl daemon-reload failed: {reload_result.stderr.strip()}")
        raise typer.Exit(1)

    enable_result = _run_systemctl("enable", "--now", TIMER_NAME)
    if enable_result.returncode != 0:
        console.print(f"[red]✗[/red] Failed to enable timer: {enable_result.stderr.strip()}")
        raise typer.Exit(1)

    console.print(f"[green]✓[/green] Installed {TIMER_NAME}")
    console.print()
    console.print("[yellow]Note:[/yellow] Ensure lingering is enabled so the timer runs while "
                  "you're logged out:")
    console.print("  loginctl enable-linger $(whoami)")


@schedule_app.command("status")
def schedule_status() -> None:
    """Show the status and next run time of the scheduled backup timer."""
    result = _run_systemctl(
        "list-timers", "--all", TIMER_NAME, "--no-pager"
    )
    console.print(result.stdout.strip() or "(no output)")

    show = _run_systemctl(
        "show", TIMER_NAME, "--property=ActiveState,NextElapseUSecRealtime,LastTriggerUSec"
    )
    if show.returncode == 0 and show.stdout.strip():
        console.print(show.stdout.strip())


@schedule_app.command("uninstall")
def schedule_uninstall() -> None:
    """Stop and remove the scheduled backup timer."""
    _run_systemctl("disable", "--now", TIMER_NAME)

    unit_dir = _systemd_user_dir()
    removed = False
    for name in (TIMER_NAME, SERVICE_NAME):
        path = unit_dir / name
        if path.exists():
            path.unlink()
            removed = True

    _run_systemctl("daemon-reload")

    if removed:
        console.print(f"[green]✓[/green] Removed scheduled backup units")
    else:
        console.print("[yellow]![/yellow] No scheduled backup units were installed")
