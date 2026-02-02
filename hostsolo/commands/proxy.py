"""Proxy management commands for Traefik."""

from pathlib import Path

import typer
from rich.console import Console

from hostsolo.config import get_project_root, load_config

app = typer.Typer()
console = Console()


def get_traefik_compose_path(local: bool = False) -> Path:
    """Get the path to the Traefik docker-compose file."""
    project_root = get_project_root()
    return project_root / "traefik" / "docker-compose.yml"


def ensure_traefik_config(local: bool = False) -> None:
    """Ensure Traefik configuration files exist."""
    from hostsolo.templates import render_traefik_compose

    project_root = get_project_root()
    config = load_config()

    traefik_dir = project_root / "traefik"
    traefik_dir.mkdir(exist_ok=True)

    # Render and write docker-compose.yml
    compose_content = render_traefik_compose(config, local=local)
    compose_path = traefik_dir / "docker-compose.yml"
    with open(compose_path, "w") as f:
        f.write(compose_content)

    # Create acme.json for Let's Encrypt certificates (must have restricted permissions)
    acme_path = traefik_dir / "acme.json"
    if not acme_path.exists():
        acme_path.touch(mode=0o600)

    # Create dynamic configuration directory
    dynamic_dir = traefik_dir / "dynamic"
    dynamic_dir.mkdir(exist_ok=True)


@app.command()
def up(
    local: bool = typer.Option(False, "--local", "-l", help="Run in local development mode"),
    detach: bool = typer.Option(True, "--detach/--no-detach", "-d", help="Run in background"),
) -> None:
    """Start the Traefik reverse proxy."""
    import subprocess

    ensure_traefik_config(local=local)
    compose_path = get_traefik_compose_path(local=local)

    console.print("[bold]Starting Traefik proxy...[/bold]")

    cmd = ["docker", "compose", "-f", str(compose_path), "up"]
    if detach:
        cmd.append("-d")

    result = subprocess.run(cmd, cwd=compose_path.parent)

    if result.returncode == 0:
        if local:
            console.print("[green]✓[/green] Traefik started in local mode")
            console.print("  Dashboard: http://localhost:8080")
        else:
            console.print("[green]✓[/green] Traefik started")
            console.print("  SSL certificates will be automatically obtained")
    else:
        console.print("[red]✗[/red] Failed to start Traefik")
        raise typer.Exit(1)


@app.command()
def down() -> None:
    """Stop the Traefik reverse proxy."""
    import subprocess

    compose_path = get_traefik_compose_path()

    if not compose_path.exists():
        console.print("[yellow]![/yellow] Traefik is not configured")
        raise typer.Exit(1)

    console.print("[bold]Stopping Traefik proxy...[/bold]")

    cmd = ["docker", "compose", "-f", str(compose_path), "down"]
    result = subprocess.run(cmd, cwd=compose_path.parent)

    if result.returncode == 0:
        console.print("[green]✓[/green] Traefik stopped")
    else:
        console.print("[red]✗[/red] Failed to stop Traefik")
        raise typer.Exit(1)


@app.command()
def logs(
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
    tail: int = typer.Option(100, "--tail", "-n", help="Number of lines to show"),
) -> None:
    """Show Traefik logs."""
    import subprocess

    compose_path = get_traefik_compose_path()

    if not compose_path.exists():
        console.print("[yellow]![/yellow] Traefik is not configured")
        raise typer.Exit(1)

    cmd = ["docker", "compose", "-f", str(compose_path), "logs", f"--tail={tail}"]
    if follow:
        cmd.append("-f")

    subprocess.run(cmd, cwd=compose_path.parent)


@app.command()
def restart() -> None:
    """Restart the Traefik reverse proxy."""
    import subprocess

    compose_path = get_traefik_compose_path()

    if not compose_path.exists():
        console.print("[yellow]![/yellow] Traefik is not configured")
        raise typer.Exit(1)

    console.print("[bold]Restarting Traefik proxy...[/bold]")

    cmd = ["docker", "compose", "-f", str(compose_path), "restart"]
    result = subprocess.run(cmd, cwd=compose_path.parent)

    if result.returncode == 0:
        console.print("[green]✓[/green] Traefik restarted")
    else:
        console.print("[red]✗[/red] Failed to restart Traefik")
        raise typer.Exit(1)
