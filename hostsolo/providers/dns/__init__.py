"""DNS provider implementations."""

from hostsolo.providers.dns.base import DNSProvider
from hostsolo.providers.dns.dnsimple import DNSimpleProvider

__all__ = ["DNSProvider", "DNSimpleProvider"]
