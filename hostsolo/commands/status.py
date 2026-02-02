"""Status command to show system overview."""

import typer
from rich.console import Console
from rich.table import Table

from hostsolo.config import get_full_domain, get_project_root, load_config

console = Console()


def show() -> None:
    """Show status of all deployments."""
    import subprocess

    try:
        config = load_config()
    except FileNotFoundError:
        console.print("[yellow]![/yellow] No hostsolo.yaml found. Run 'hostsolo init' first.")
        raise typer.Exit(1)

    project_root = get_project_root()

    console.print(f"[bold]Host Solo Status[/bold]")
    console.print(f"Domain: {config.domain}")
    console.print()

    # Check Traefik status
    console.print("[bold]Proxy (Traefik)[/bold]")
    traefik_compose = project_root / "traefik" / "docker-compose.yml"
    if traefik_compose.exists():
        result = subprocess.run(
            ["docker", "compose", "-f", str(traefik_compose), "ps", "--format", "json"],
            capture_output=True,
            text=True,
            cwd=traefik_compose.parent,
        )
        if result.returncode == 0 and result.stdout.strip():
            import json

            try:
                containers = json.loads(f"[{result.stdout.strip().replace(chr(10), ',')}]")
                for container in containers:
                    status = container.get("State", "unknown")
                    name = container.get("Name", "traefik")
                    if status == "running":
                        console.print(f"  [green]●[/green] {name}: running")
                    else:
                        console.print(f"  [red]●[/red] {name}: {status}")
            except json.JSONDecodeError:
                console.print("  [yellow]●[/yellow] Unable to parse status")
        else:
            console.print("  [dim]●[/dim] Not running")
    else:
        console.print("  [dim]●[/dim] Not configured")

    console.print()

    # Check app status per environment
    console.print("[bold]Applications[/bold]")

    table = Table()
    table.add_column("Environment")
    table.add_column("App")
    table.add_column("Status")
    table.add_column("Domain")

    apps_dir = project_root / "apps"
    if apps_dir.exists():
        for env_dir in sorted(apps_dir.iterdir()):
            if env_dir.is_dir():
                env_name = env_dir.name
                for app_dir in sorted(env_dir.iterdir()):
                    if app_dir.is_dir():
                        app_name = app_dir.name
                        compose_file = app_dir / "docker-compose.yml"

                        if compose_file.exists():
                            result = subprocess.run(
                                [
                                    "docker",
                                    "compose",
                                    "-f",
                                    str(compose_file),
                                    "ps",
                                    "--format",
                                    "json",
                                ],
                                capture_output=True,
                                text=True,
                                cwd=app_dir,
                            )

                            if result.returncode == 0 and result.stdout.strip():
                                import json

                                try:
                                    containers = json.loads(
                                        f"[{result.stdout.strip().replace(chr(10), ',')}]"
                                    )
                                    running = all(
                                        c.get("State") == "running" for c in containers
                                    )
                                    if running:
                                        status = "[green]running[/green]"
                                    else:
                                        status = "[yellow]partial[/yellow]"
                                except json.JSONDecodeError:
                                    status = "[yellow]unknown[/yellow]"
                            else:
                                status = "[dim]stopped[/dim]"

                            try:
                                domain = get_full_domain(config, env_name)
                            except ValueError:
                                domain = "-"

                            table.add_row(env_name, app_name, status, domain)

    if table.row_count == 0:
        console.print("  No apps deployed")
    else:
        console.print(table)

    console.print()

    # Show configured environments
    console.print("[bold]Environments[/bold]")
    for env_name, env_config in config.environments.items():
        domain = get_full_domain(config, env_name)
        console.print(f"  {env_name}: {domain}")
