"""DNSimple DNS provider implementation."""

from typing import Any

import httpx

from hostsolo.providers.dns.base import DNSProvider


class DNSimpleProvider(DNSProvider):
    """DNS provider implementation for DNSimple."""

    BASE_URL = "https://api.dnsimple.com/v2"

    def __init__(self, token: str, account_id: str):
        """Initialize DNSimple provider.

        Args:
            token: DNSimple API token
            account_id: DNSimple account ID
        """
        self.token = token
        self.account_id = account_id
        self.client = httpx.Client(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def _get_zone_id(self, domain: str) -> str:
        """Get the zone ID for a domain (DNSimple uses domain name as zone)."""
        return domain

    def list_records(self, domain: str) -> list[dict[str, Any]]:
        """List all DNS records for a domain."""
        response = self.client.get(
            f"/{self.account_id}/zones/{domain}/records"
        )
        response.raise_for_status()

        data = response.json()
        records = []

        for record in data.get("data", []):
            records.append({
                "id": record["id"],
                "type": record["type"],
                "name": record["name"] or "@",
                "content": record["content"],
                "ttl": record["ttl"],
            })

        return records

    def _find_record(
        self, domain: str, name: str, record_type: str
    ) -> dict[str, Any] | None:
        """Find a specific record by name and type."""
        records = self.list_records(domain)
        # DNSimple uses empty string for root, we use "@"
        search_name = "" if name == "@" else name

        for record in records:
            record_name = record["name"] if record["name"] != "@" else ""
            if record_name == search_name and record["type"] == record_type:
                return record

        return None

    def upsert_a_record(self, domain: str, name: str, ip: str, ttl: int = 3600) -> None:
        """Create or update an A record."""
        existing = self._find_record(domain, name, "A")

        # DNSimple uses empty string for root
        record_name = "" if name == "@" else name

        if existing:
            # Update existing record
            response = self.client.patch(
                f"/{self.account_id}/zones/{domain}/records/{existing['id']}",
                json={
                    "content": ip,
                    "ttl": ttl,
                },
            )
        else:
            # Create new record
            response = self.client.post(
                f"/{self.account_id}/zones/{domain}/records",
                json={
                    "name": record_name,
                    "type": "A",
                    "content": ip,
                    "ttl": ttl,
                },
            )

        response.raise_for_status()

    def delete_a_record(self, domain: str, name: str) -> None:
        """Delete an A record."""
        existing = self._find_record(domain, name, "A")

        if existing:
            response = self.client.delete(
                f"/{self.account_id}/zones/{domain}/records/{existing['id']}"
            )
            response.raise_for_status()

    def upsert_cname_record(
        self, domain: str, name: str, target: str, ttl: int = 3600
    ) -> None:
        """Create or update a CNAME record."""
        existing = self._find_record(domain, name, "CNAME")

        if existing:
            response = self.client.patch(
                f"/{self.account_id}/zones/{domain}/records/{existing['id']}",
                json={
                    "content": target,
                    "ttl": ttl,
                },
            )
        else:
            response = self.client.post(
                f"/{self.account_id}/zones/{domain}/records",
                json={
                    "name": name,
                    "type": "CNAME",
                    "content": target,
                    "ttl": ttl,
                },
            )

        response.raise_for_status()
