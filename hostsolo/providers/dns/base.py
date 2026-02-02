"""Abstract base class for DNS providers."""

from abc import ABC, abstractmethod
from typing import Any


class DNSProvider(ABC):
    """Abstract DNS provider interface."""

    @abstractmethod
    def list_records(self, domain: str) -> list[dict[str, Any]]:
        """List all DNS records for a domain.

        Args:
            domain: The domain name (e.g., "example.com")

        Returns:
            List of record dictionaries with keys: type, name, content, ttl
        """
        pass

    @abstractmethod
    def upsert_a_record(self, domain: str, name: str, ip: str, ttl: int = 3600) -> None:
        """Create or update an A record.

        Args:
            domain: The domain name (e.g., "example.com")
            name: The record name (e.g., "www" or "@" for root)
            ip: The IP address to point to
            ttl: Time to live in seconds (default: 3600)
        """
        pass

    @abstractmethod
    def delete_a_record(self, domain: str, name: str) -> None:
        """Delete an A record.

        Args:
            domain: The domain name (e.g., "example.com")
            name: The record name (e.g., "www" or "@" for root)
        """
        pass

    @abstractmethod
    def upsert_cname_record(
        self, domain: str, name: str, target: str, ttl: int = 3600
    ) -> None:
        """Create or update a CNAME record.

        Args:
            domain: The domain name (e.g., "example.com")
            name: The record name (e.g., "www")
            target: The target domain (e.g., "example.com")
            ttl: Time to live in seconds (default: 3600)
        """
        pass
