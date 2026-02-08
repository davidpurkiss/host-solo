"""CLI entry point for Host Solo."""

import typer
from rich.console import Console

from hostsolo import __version__
from hostsolo.commands import backup, deploy, dns, env, proxy, status

app = typer.Typer(
    name="hostsolo",
    help="Lightweight self-hosted application platform for VPS deployments.",
    no_args_is_help=True,
)
console = Console()

# Register sub-commands
app.add_typer(proxy.app, name="proxy", help="Manage the Traefik reverse proxy")
app.add_typer(deploy.app, name="deploy", help="Deploy applications")
app.add_typer(dns.app, name="dns", help="Manage DNS records")
app.add_typer(backup.app, name="backup", help="Manage backups")
app.add_typer(env.app, name="env", help="Manage environments")


@app.command()
def init(
    domain: str = typer.Option(..., prompt="Enter your domain", help="Your domain name"),
    email: str = typer.Option(
        ..., prompt="Enter your email (for Let's Encrypt)", help="Email for SSL certificates"
    ),
) -> None:
    """Initialize a new Host Solo project."""
    from pathlib import Path

    import yaml

    config_path = Path.cwd() / "hostsolo.yaml"

    if config_path.exists():
        overwrite = typer.confirm("hostsolo.yaml already exists. Overwrite?")
        if not overwrite:
            raise typer.Abort()

    config = {
        "domain": domain,
        "email": email,
        "data_dir": "./data",
        "dns": {"provider": "dnsimple"},
        "backup": {
            "provider": "s3",
            "bucket": "my-backups",
            "schedule": "0 */6 * * *",
        },
        "environments": {
            "dev": {"subdomain": "dev"},
            "staging": {"subdomain": "staging"},
            "prod": {"subdomain": ""},
        },
        "apps": {
            "directus": {
                "image": "directus/directus",
                "tag": "10.10.5",
                "ports": ["8055"],
                "volumes": [
                    "./data/${ENV}/directus/database:/directus/database",
                    "./data/${ENV}/directus/uploads:/directus/uploads",
                ],
                "environment": {
                    "DB_CLIENT": "sqlite3",
                    "DB_FILENAME": "/directus/database/data.db",
                },
                "backup_paths": ["./data/${ENV}/directus/database"],
            }
        },
    }

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    # Create .env.example for hostsolo CLI credentials
    env_example_path = Path.cwd() / ".env.example"
    env_content = """# Host Solo CLI Environment Variables
# Copy this to .env and fill in your credentials

# DNS Provider (DNSimple)
HOSTSOLO_DNSIMPLE_TOKEN=your-dnsimple-token
HOSTSOLO_DNSIMPLE_ACCOUNT_ID=your-account-id

# Backup Provider (S3-compatible)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1

# For S3-compatible providers like Backblaze B2 or MinIO:
# S3_ENDPOINT_URL=https://s3.us-west-000.backblazeb2.com
"""
    with open(env_example_path, "w") as f:
        f.write(env_content)

    # Create data directory
    data_dir = Path.cwd() / "data"
    data_dir.mkdir(exist_ok=True)

    # Create config directory and per-app config directories
    config_dir = Path.cwd() / "config"
    config_dir.mkdir(exist_ok=True)

    # Create per-app config directories based on apps in hostsolo.yaml
    for app_name in config["apps"].keys():
        app_config_dir = config_dir / app_name
        app_config_dir.mkdir(exist_ok=True)

        # Create env.example for this app
        env_example = app_config_dir / "env.example"
        app_env_content = f"""# Environment variables for {app_name}
# Copy this file to shared.env, dev.env, staging.env, and prod.env
# shared.env: Values shared across all environments
# {{env}}.env: Environment-specific values (override shared)

# Example variables (customize for your app):
# KEY=your-secret-key
# SECRET=your-secret
# ADMIN_PASSWORD=change-me
"""
        with open(env_example, "w") as f:
            f.write(app_env_content)

        console.print(f"[green]✓[/green] Created config/{app_name}/ directory")

    # Create .gitignore
    gitignore_path = Path.cwd() / ".gitignore"
    gitignore_content = """# Host Solo
.env
data/
*.log
acme.json

# App config (secrets) - keep env.example, exclude actual env files
config/*/*.env
!config/*/env.example
"""
    if not gitignore_path.exists():
        with open(gitignore_path, "w") as f:
            f.write(gitignore_content)
    else:
        # Append config exclusion if not present
        with open(gitignore_path, "r") as f:
            existing = f.read()
        if "config/*/*.env" not in existing:
            with open(gitignore_path, "a") as f:
                f.write("""
# App config (secrets) - keep env.example, exclude actual env files
config/*/*.env
!config/*/env.example
""")

    console.print("[green]✓[/green] Created hostsolo.yaml")
    console.print("[green]✓[/green] Created .env.example")
    console.print("[green]✓[/green] Created data/ directory")
    console.print("[green]✓[/green] Created/updated .gitignore")
    console.print()
    console.print("Next steps:")
    console.print("  1. Copy .env.example to .env and fill in DNS/backup credentials")
    console.print("  2. For each app, set up environment configs:")
    console.print("     cp config/<app>/env.example config/<app>/shared.env")
    console.print("     cp config/<app>/env.example config/<app>/dev.env")
    console.print("     cp config/<app>/env.example config/<app>/prod.env")
    console.print("  3. Edit hostsolo.yaml to customize your apps")
    console.print("  4. Run [bold]hostsolo proxy up[/bold] to start Traefik")
    console.print("  5. Run [bold]hostsolo deploy up <app> --env <env>[/bold] to deploy")


@app.command()
def version() -> None:
    """Show the Host Solo version."""
    console.print(f"Host Solo v{__version__}")


@app.callback()
def main() -> None:
    """Host Solo - Lightweight self-hosted application platform."""
    pass


# Also expose status command at root level
app.command(name="status")(status.show)

if __name__ == "__main__":
    app()
