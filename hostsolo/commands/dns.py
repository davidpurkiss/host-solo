"""DNS management commands."""

import typer
from rich.console import Console
from rich.table import Table

from hostsolo.config import get_dns_zone_and_record, get_full_domain, load_config, load_env_settings

app = typer.Typer()
console = Console()


def get_dns_provider():
    """Get the configured DNS provider."""
    from hostsolo.providers.dns import DNSimpleProvider

    config = load_config()
    settings = load_env_settings()

    if config.dns.provider == "dnsimple":
        if not settings.dnsimple_token or not settings.dnsimple_account_id:
            console.print("[red]✗[/red] DNSimple credentials not configured")
            console.print("  Set HOSTSOLO_DNSIMPLE_TOKEN and HOSTSOLO_DNSIMPLE_ACCOUNT_ID")
            raise typer.Exit(1)
        return DNSimpleProvider(
            token=settings.dnsimple_token,
            account_id=settings.dnsimple_account_id,
        )
    else:
        console.print(f"[red]✗[/red] Unknown DNS provider: {config.dns.provider}")
        raise typer.Exit(1)


def get_public_ip() -> str:
    """Get the public IP address of this machine."""
    import httpx

    try:
        # Try multiple services for reliability
        services = [
            "https://api.ipify.org",
            "https://ifconfig.me/ip",
            "https://icanhazip.com",
        ]
        for service in services:
            try:
                response = httpx.get(service, timeout=5.0)
                if response.status_code == 200:
                    return response.text.strip()
            except httpx.RequestError:
                continue
        raise RuntimeError("Could not determine public IP")
    except Exception as e:
        console.print(f"[red]✗[/red] Could not determine public IP: {e}")
        raise typer.Exit(1)


@app.command()
def setup(
    env_name: str = typer.Option("prod", "--env", "-e", help="Target environment"),
    ip: str | None = typer.Option(None, "--ip", help="IP address (auto-detected if not provided)"),
) -> None:
    """Set up DNS records for an environment."""
    config = load_config()
    provider = get_dns_provider()

    domain = get_full_domain(config, env_name)
    zone, record_name = get_dns_zone_and_record(config, env_name)
    target_ip = ip or get_public_ip()

    console.print(f"[bold]Setting up DNS for {domain}...[/bold]")
    console.print(f"  IP: {target_ip}")

    try:
        provider.upsert_a_record(
            domain=zone,
            name=record_name,
            ip=target_ip,
        )
        console.print(f"[green]✓[/green] A record created/updated: {domain} → {target_ip}")
        console.print()
        console.print("[yellow]Note:[/yellow] DNS propagation may take a few minutes")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to set up DNS: {e}")
        raise typer.Exit(1)


@app.command("list")
def list_records() -> None:
    """List all DNS records for the domain."""
    config = load_config()
    provider = get_dns_provider()

    zone = config.dns.zone or config.domain

    console.print(f"[bold]DNS records for {zone}[/bold]")

    try:
        records = provider.list_records(zone)

        table = Table()
        table.add_column("Type")
        table.add_column("Name")
        table.add_column("Content")
        table.add_column("TTL")

        for record in records:
            table.add_row(
                record["type"],
                record["name"],
                record["content"],
                str(record.get("ttl", "-")),
            )

        console.print(table)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to list records: {e}")
        raise typer.Exit(1)


@app.command()
def delete(
    env_name: str = typer.Option("prod", "--env", "-e", help="Target environment"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete DNS records for an environment."""
    config = load_config()
    provider = get_dns_provider()

    domain = get_full_domain(config, env_name)
    zone, record_name = get_dns_zone_and_record(config, env_name)

    if not force:
        confirm = typer.confirm(f"Delete DNS record for {domain}?")
        if not confirm:
            raise typer.Abort()

    console.print(f"[bold]Deleting DNS record for {domain}...[/bold]")

    try:
        provider.delete_a_record(domain=zone, name=record_name)
        console.print(f"[green]✓[/green] A record deleted: {domain}")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to delete DNS record: {e}")
        raise typer.Exit(1)
