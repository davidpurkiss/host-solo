"""Deploy command for applications."""

from pathlib import Path

import typer
from rich.console import Console

from hostsolo.config import get_full_domain, get_project_root, load_config

app = typer.Typer()
console = Console()


def ensure_env_files(app_name: str, env_name: str) -> None:
    """Ensure environment config files exist for the app.

    Args:
        app_name: Name of the application
        env_name: Target environment name

    Raises:
        typer.Exit: If required config files are missing
    """
    project_root = get_project_root()
    app_config_dir = project_root / "config" / app_name

    shared_env = app_config_dir / "shared.env"
    env_specific = app_config_dir / f"{env_name}.env"

    if not app_config_dir.exists():
        console.print(f"[red]✗[/red] Missing config/{app_name}/ directory")
        console.print(f"  Run 'hostsolo init' or create the directory manually")
        console.print(f"  Then copy config/{app_name}/env.example to shared.env and {env_name}.env")
        raise typer.Exit(1)

    missing_files = []
    if not shared_env.exists():
        missing_files.append(f"config/{app_name}/shared.env")
    if not env_specific.exists():
        missing_files.append(f"config/{app_name}/{env_name}.env")

    if missing_files:
        console.print(f"[red]✗[/red] Missing environment files:")
        for f in missing_files:
            console.print(f"  - {f}")
        console.print()
        console.print("Create these files from the example:")
        if (app_config_dir / "env.example").exists():
            console.print(f"  cp config/{app_name}/env.example config/{app_name}/shared.env")
            console.print(f"  cp config/{app_name}/env.example config/{app_name}/{env_name}.env")
        else:
            console.print(f"  touch config/{app_name}/shared.env")
            console.print(f"  touch config/{app_name}/{env_name}.env")
        raise typer.Exit(1)


def get_app_compose_path(app_name: str, env_name: str) -> Path:
    """Get the path to an app's docker-compose file."""
    project_root = get_project_root()
    return project_root / "apps" / env_name / app_name / "docker-compose.yml"


def ensure_app_config(app_name: str, env_name: str, tag: str | None = None, local: bool = False) -> Path:
    """Ensure app configuration files exist and return the compose path."""
    from hostsolo.templates import render_app_compose

    project_root = get_project_root()
    config = load_config()

    # These are already validated in deploy_app, but keep for safety in case
    # this function is called directly
    if app_name not in config.apps:
        console.print(f"[red]✗[/red] App '{app_name}' not found in configuration")
        raise typer.Exit(1)

    if env_name not in config.environments:
        console.print(f"[red]✗[/red] Environment '{env_name}' not found in configuration")
        raise typer.Exit(1)

    app_config = config.apps[app_name]
    if tag:
        # Create a copy with the new tag
        app_config = app_config.model_copy(update={"tag": tag})

    # Create app directory structure
    app_dir = project_root / "apps" / env_name / app_name
    app_dir.mkdir(parents=True, exist_ok=True)

    # Create data directories
    data_base = project_root / "data" / env_name / app_name
    data_base.mkdir(parents=True, exist_ok=True)

    # Render and write docker-compose.yml
    domain = get_full_domain(config, env_name)
    compose_content = render_app_compose(
        config=config,
        app_name=app_name,
        app_config=app_config,
        env_name=env_name,
        domain=domain,
        local=local,
    )

    compose_path = app_dir / "docker-compose.yml"
    with open(compose_path, "w") as f:
        f.write(compose_content)

    return compose_path


@app.command("up")
def deploy_up(
    app_name: str = typer.Argument(..., help="Name of the app to deploy"),
    env_name: str = typer.Option("prod", "--env", "-e", help="Target environment"),
    tag: str | None = typer.Option(None, "--tag", "-t", help="Docker image tag to deploy"),
    local: bool = typer.Option(False, "--local", "-l", help="Deploy in local mode"),
    pull: bool = typer.Option(True, "--pull/--no-pull", help="Pull latest image before deploying"),
) -> None:
    """Deploy an application to an environment."""
    import subprocess

    config = load_config()

    # Validate app exists
    if app_name not in config.apps:
        console.print(f"[red]✗[/red] App '{app_name}' not found in configuration")
        raise typer.Exit(1)

    # Validate environment exists
    if env_name not in config.environments:
        console.print(f"[red]✗[/red] Environment '{env_name}' not found in configuration")
        raise typer.Exit(1)

    # Ensure env files exist
    ensure_env_files(app_name, env_name)

    domain = get_full_domain(config, env_name)

    console.print(f"[bold]Deploying {app_name} to {env_name}...[/bold]")
    console.print(f"  Domain: {domain}")

    if tag:
        console.print(f"  Tag: {tag}")

    compose_path = ensure_app_config(app_name, env_name, tag=tag, local=local)

    # Pull latest image
    if pull:
        console.print("  Pulling latest image...")
        cmd = ["docker", "compose", "-f", str(compose_path), "pull"]
        subprocess.run(cmd, cwd=compose_path.parent, capture_output=True)

    # Start the app
    cmd = ["docker", "compose", "-f", str(compose_path), "up", "-d", "--remove-orphans"]
    result = subprocess.run(cmd, cwd=compose_path.parent)

    if result.returncode == 0:
        console.print(f"[green]✓[/green] {app_name} deployed to {env_name}")
        if local:
            console.print(f"  URL: http://{domain}")
        else:
            console.print(f"  URL: https://{domain}")
    else:
        console.print(f"[red]✗[/red] Failed to deploy {app_name}")
        raise typer.Exit(1)


@app.command()
def stop(
    app_name: str = typer.Argument(..., help="Name of the app to stop"),
    env_name: str = typer.Option("prod", "--env", "-e", help="Target environment"),
) -> None:
    """Stop a deployed application."""
    import subprocess

    compose_path = get_app_compose_path(app_name, env_name)

    if not compose_path.exists():
        console.print(f"[yellow]![/yellow] {app_name} is not deployed in {env_name}")
        raise typer.Exit(1)

    console.print(f"[bold]Stopping {app_name} in {env_name}...[/bold]")

    cmd = ["docker", "compose", "-f", str(compose_path), "down"]
    result = subprocess.run(cmd, cwd=compose_path.parent)

    if result.returncode == 0:
        console.print(f"[green]✓[/green] {app_name} stopped")
    else:
        console.print(f"[red]✗[/red] Failed to stop {app_name}")
        raise typer.Exit(1)


@app.command()
def logs(
    app_name: str = typer.Argument(..., help="Name of the app"),
    env_name: str = typer.Option("prod", "--env", "-e", help="Target environment"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
    tail: int = typer.Option(100, "--tail", "-n", help="Number of lines to show"),
) -> None:
    """Show application logs."""
    import subprocess

    compose_path = get_app_compose_path(app_name, env_name)

    if not compose_path.exists():
        console.print(f"[yellow]![/yellow] {app_name} is not deployed in {env_name}")
        raise typer.Exit(1)

    cmd = ["docker", "compose", "-f", str(compose_path), "logs", f"--tail={tail}"]
    if follow:
        cmd.append("-f")

    subprocess.run(cmd, cwd=compose_path.parent)


@app.command()
def restart(
    app_name: str = typer.Argument(..., help="Name of the app to restart"),
    env_name: str = typer.Option("prod", "--env", "-e", help="Target environment"),
) -> None:
    """Restart a deployed application."""
    import subprocess

    compose_path = get_app_compose_path(app_name, env_name)

    if not compose_path.exists():
        console.print(f"[yellow]![/yellow] {app_name} is not deployed in {env_name}")
        raise typer.Exit(1)

    console.print(f"[bold]Restarting {app_name} in {env_name}...[/bold]")

    cmd = ["docker", "compose", "-f", str(compose_path), "restart"]
    result = subprocess.run(cmd, cwd=compose_path.parent)

    if result.returncode == 0:
        console.print(f"[green]✓[/green] {app_name} restarted")
    else:
        console.print(f"[red]✗[/red] Failed to restart {app_name}")
        raise typer.Exit(1)
