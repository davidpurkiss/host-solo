"""Configuration management for Host Solo."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import AliasChoices, BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DNSConfig(BaseModel):
    """DNS provider configuration."""

    provider: str = "dnsimple"
    zone: str = ""  # DNS zone (e.g. "example.com"). Defaults to config.domain


class BackupConfig(BaseModel):
    """Backup provider configuration."""

    provider: str = "s3"
    bucket: str = ""
    endpoint_url: str | None = None  # For S3-compatible providers like MinIO
    schedule: str = "0 */6 * * *"  # Cron expression


class EnvironmentConfig(BaseModel):
    """Environment-specific configuration."""

    subdomain: str = ""  # Empty string means root domain


class AppVolumeConfig(BaseModel):
    """Volume configuration for an app."""

    source: str
    target: str


class AppConfig(BaseModel):
    """Application configuration."""

    image: str
    tag: str = "latest"
    ports: list[str] = Field(default_factory=list)
    volumes: list[str] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    command: list[str] = Field(default_factory=list)
    packages: list[str] = Field(default_factory=list)
    backup_paths: list[str] = Field(default_factory=list)
    healthcheck_path: str | None = None
    replicas: int = 1


class HostSoloConfig(BaseModel):
    """Main configuration for Host Solo."""

    domain: str
    email: str  # For Let's Encrypt
    data_dir: str = "./data"
    dns: DNSConfig = Field(default_factory=DNSConfig)
    backup: BackupConfig = Field(default_factory=BackupConfig)
    environments: dict[str, EnvironmentConfig] = Field(default=None, validate_default=True)
    apps: dict[str, AppConfig] = Field(default_factory=dict)

    @field_validator("environments", mode="before")
    @classmethod
    def set_default_environments(
        cls, v: dict[str, Any] | None
    ) -> dict[str, EnvironmentConfig]:
        if not v:
            return {
                "dev": EnvironmentConfig(subdomain="dev"),
                "staging": EnvironmentConfig(subdomain="staging"),
                "prod": EnvironmentConfig(subdomain=""),
            }
        return {k: EnvironmentConfig(**val) if isinstance(val, dict) else val for k, val in v.items()}


class EnvironmentSettings(BaseSettings):
    """Environment variables for sensitive configuration."""

    model_config = SettingsConfigDict(
        env_prefix="HOSTSOLO_", env_file=".env", populate_by_name=True
    )

    # DNS provider credentials
    dnsimple_token: str | None = None
    dnsimple_account_id: str | None = None

    # Backup provider credentials (S3-compatible).
    # These use the conventional AWS_* names (no HOSTSOLO_ prefix) so the same
    # variables boto3/awscli expect work unchanged. AliasChoices bypasses the
    # model-wide env_prefix; the prefixed form is also accepted as a fallback.
    aws_access_key_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AWS_ACCESS_KEY_ID", "HOSTSOLO_AWS_ACCESS_KEY_ID"),
    )
    aws_secret_access_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AWS_SECRET_ACCESS_KEY", "HOSTSOLO_AWS_SECRET_ACCESS_KEY"),
    )
    aws_region: str = Field(
        default="us-east-1",
        validation_alias=AliasChoices("AWS_REGION", "HOSTSOLO_AWS_REGION"),
    )

    # App secrets (can be extended)
    directus_key: str | None = None
    directus_secret: str | None = None


def find_config_file(start_path: Path | None = None) -> Path | None:
    """Find hostsolo.yaml in current or parent directories."""
    search_path = start_path or Path.cwd()

    for path in [search_path, *search_path.parents]:
        config_file = path / "hostsolo.yaml"
        if config_file.exists():
            return config_file
        config_file = path / "hostsolo.yml"
        if config_file.exists():
            return config_file

    return None


def load_config(config_path: Path | None = None) -> HostSoloConfig:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = find_config_file()

    if config_path is None or not config_path.exists():
        raise FileNotFoundError(
            "No hostsolo.yaml found. Run 'hostsolo init' to create one."
        )

    with open(config_path) as f:
        data = yaml.safe_load(f)

    return HostSoloConfig(**data)


def load_env_settings() -> EnvironmentSettings:
    """Load environment settings from .env and environment variables."""
    return EnvironmentSettings()


def get_full_domain(config: HostSoloConfig, env_name: str) -> str:
    """Get the full domain for an environment."""
    env_config = config.environments.get(env_name)
    if env_config is None:
        raise ValueError(f"Environment '{env_name}' not found in configuration")

    if env_config.subdomain:
        return f"{env_config.subdomain}.{config.domain}"
    return config.domain


def get_dns_zone_and_record(config: HostSoloConfig, env_name: str) -> tuple[str, str]:
    """Get the DNS zone and record name for an environment.

    Returns:
        Tuple of (zone, record_name). record_name is "@" for zone apex.
    """
    zone = config.dns.zone or config.domain
    full_domain = get_full_domain(config, env_name)

    if full_domain == zone:
        return zone, "@"

    # Strip the zone suffix to get the record name
    if full_domain.endswith(f".{zone}"):
        record_name = full_domain[: -(len(zone) + 1)]
        return zone, record_name

    # Zone doesn't match domain — fall back to using domain as zone
    env_config = config.environments[env_name]
    return config.domain, env_config.subdomain or "@"


def get_data_path(config: HostSoloConfig, env_name: str, app_name: str) -> Path:
    """Get the data directory path for an app in an environment."""
    return Path(config.data_dir) / env_name / app_name


def get_project_root() -> Path:
    """Get the project root directory (where hostsolo.yaml is located)."""
    config_file = find_config_file()
    if config_file:
        return config_file.parent
    return Path.cwd()


class _LiteralBlockDumper(yaml.SafeDumper):
    pass


def _str_representer(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_LiteralBlockDumper.add_representer(str, _str_representer)


def dump_yaml(data: dict, stream=None) -> str | None:
    """Dump data to YAML, preserving multiline strings as literal blocks."""
    return yaml.dump(
        data,
        stream=stream,
        Dumper=_LiteralBlockDumper,
        default_flow_style=False,
        sort_keys=False,
    )
