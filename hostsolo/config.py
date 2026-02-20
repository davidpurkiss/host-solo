"""Configuration management for Host Solo."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DNSConfig(BaseModel):
    """DNS provider configuration."""

    provider: str = "dnsimple"


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

    model_config = SettingsConfigDict(env_prefix="HOSTSOLO_", env_file=".env")

    # DNS provider credentials
    dnsimple_token: str | None = None
    dnsimple_account_id: str | None = None

    # Backup provider credentials (S3-compatible)
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str = "us-east-1"

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
