"""Environment management commands."""

import typer
from rich.console import Console
from rich.table import Table

from hostsolo.config import get_full_domain, load_config

app = typer.Typer()
console = Console()


@app.command("list")
def list_envs() -> None:
    """List all configured environments."""
    config = load_config()

    table = Table()
    table.add_column("Environment")
    table.add_column("Subdomain")
    table.add_column("Full Domain")

    for env_name, env_config in config.environments.items():
        subdomain = env_config.subdomain or "(root)"
        full_domain = get_full_domain(config, env_name)
        table.add_row(env_name, subdomain, full_domain)

    console.print(table)


@app.command()
def create(
    name: str = typer.Argument(..., help="Environment name"),
    subdomain: str = typer.Option(None, "--subdomain", "-s", help="Subdomain (defaults to name)"),
) -> None:
    """Create a new environment."""
    from pathlib import Path

    import yaml

    from hostsolo.config import dump_yaml, find_config_file

    config_path = find_config_file()
    if config_path is None:
        console.print("[red]✗[/red] No hostsolo.yaml found. Run 'hostsolo init' first.")
        raise typer.Exit(1)

    with open(config_path) as f:
        data = yaml.safe_load(f)

    if "environments" not in data:
        data["environments"] = {}

    if name in data["environments"]:
        console.print(f"[yellow]![/yellow] Environment '{name}' already exists")
        raise typer.Exit(1)

    data["environments"][name] = {"subdomain": subdomain or name}

    with open(config_path, "w") as f:
        dump_yaml(data, f)

    full_subdomain = subdomain or name
    console.print(f"[green]✓[/green] Created environment: {name}")
    console.print(f"  Subdomain: {full_subdomain}")


@app.command()
def destroy(
    name: str = typer.Argument(..., help="Environment name"),
    remove_data: bool = typer.Option(False, "--remove-data", help="Also remove data directory"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Destroy an environment and stop its containers."""
    import shutil
    import subprocess
    from pathlib import Path

    from hostsolo.config import find_config_file, get_project_root

    config = load_config()

    if name not in config.environments:
        console.print(f"[red]✗[/red] Environment '{name}' not found")
        raise typer.Exit(1)

    if name == "prod" and not force:
        confirm = typer.confirm(
            "You are about to destroy the production environment. Are you sure?"
        )
        if not confirm:
            raise typer.Abort()

    project_root = get_project_root()

    # Stop all apps in this environment
    apps_dir = project_root / "apps" / name
    if apps_dir.exists():
        console.print(f"[bold]Stopping apps in {name}...[/bold]")
        for app_dir in apps_dir.iterdir():
            if app_dir.is_dir():
                compose_file = app_dir / "docker-compose.yml"
                if compose_file.exists():
                    console.print(f"  Stopping {app_dir.name}...")
                    subprocess.run(
                        ["docker", "compose", "-f", str(compose_file), "down"],
                        cwd=app_dir,
                        capture_output=True,
                    )

        # Remove apps directory for this environment
        shutil.rmtree(apps_dir)
        console.print(f"[green]✓[/green] Removed app configurations")

    # Optionally remove data
    if remove_data:
        data_dir = project_root / "data" / name
        if data_dir.exists():
            if not force:
                confirm = typer.confirm(f"Delete all data in {data_dir}?")
                if not confirm:
                    console.print("  Keeping data directory")
                else:
                    shutil.rmtree(data_dir)
                    console.print(f"[green]✓[/green] Removed data directory")
            else:
                shutil.rmtree(data_dir)
                console.print(f"[green]✓[/green] Removed data directory")

    console.print(f"[green]✓[/green] Environment '{name}' destroyed")
    console.print()
    console.print(
        "[yellow]Note:[/yellow] Environment is still in hostsolo.yaml. "
        "Remove it manually if no longer needed."
    )
