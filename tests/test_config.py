"""Tests for configuration management."""

import tempfile
from pathlib import Path

import pytest
import yaml

from hostsolo.config import (
    AppConfig,
    BackupConfig,
    DNSConfig,
    EnvironmentConfig,
    HostSoloConfig,
    get_full_domain,
    load_config,
)


@pytest.fixture
def sample_config_data():
    """Return sample configuration data."""
    return {
        "domain": "example.com",
        "email": "admin@example.com",
        "data_dir": "./data",
        "dns": {"provider": "dnsimple"},
        "backup": {
            "provider": "s3",
            "bucket": "test-bucket",
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
                "volumes": ["./data/${ENV}/directus:/directus/database"],
                "environment": {"DB_CLIENT": "sqlite3"},
                "backup_paths": ["./data/${ENV}/directus"],
            }
        },
    }


@pytest.fixture
def temp_config_file(sample_config_data):
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        yaml.dump(sample_config_data, f)
        return Path(f.name)


def test_load_config(temp_config_file):
    """Test loading configuration from file."""
    config = load_config(temp_config_file)

    assert config.domain == "example.com"
    assert config.email == "admin@example.com"
    assert config.dns.provider == "dnsimple"
    assert config.backup.bucket == "test-bucket"
    assert "directus" in config.apps


def test_host_solo_config_validation():
    """Test HostSoloConfig validates correctly with default environments."""
    config = HostSoloConfig(
        domain="test.com",
        email="test@test.com",
    )

    # Should have default environments
    assert "dev" in config.environments
    assert "staging" in config.environments
    assert "prod" in config.environments


def test_host_solo_config_custom_environments():
    """Test HostSoloConfig respects custom environments."""
    config = HostSoloConfig(
        domain="test.com",
        email="test@test.com",
        environments={"custom": {"subdomain": "custom"}},
    )

    # Should only have the custom environment
    assert "custom" in config.environments
    assert "dev" not in config.environments


def test_app_config():
    """Test AppConfig model."""
    app = AppConfig(
        image="nginx",
        tag="latest",
        ports=["80"],
    )

    assert app.image == "nginx"
    assert app.tag == "latest"
    assert app.ports == ["80"]
    assert app.volumes == []  # default
    assert app.environment == {}  # default


def test_get_full_domain():
    """Test full domain generation."""
    config = HostSoloConfig(
        domain="example.com",
        email="test@test.com",
        environments={
            "dev": EnvironmentConfig(subdomain="dev"),
            "prod": EnvironmentConfig(subdomain=""),
        },
    )

    assert get_full_domain(config, "dev") == "dev.example.com"
    assert get_full_domain(config, "prod") == "example.com"


def test_get_full_domain_invalid_env():
    """Test that invalid environment raises error."""
    config = HostSoloConfig(
        domain="example.com",
        email="test@test.com",
    )

    with pytest.raises(ValueError, match="not found"):
        get_full_domain(config, "nonexistent")


def test_dns_config():
    """Test DNSConfig model."""
    dns = DNSConfig(provider="dnsimple")
    assert dns.provider == "dnsimple"


def test_backup_config():
    """Test BackupConfig model."""
    backup = BackupConfig(
        provider="s3",
        bucket="my-bucket",
        endpoint_url="https://s3.example.com",
    )

    assert backup.provider == "s3"
    assert backup.bucket == "my-bucket"
    assert backup.endpoint_url == "https://s3.example.com"
    assert backup.schedule == "0 */6 * * *"  # default


def test_environment_config():
    """Test EnvironmentConfig model."""
    env = EnvironmentConfig(subdomain="staging")
    assert env.subdomain == "staging"

    root_env = EnvironmentConfig(subdomain="")
    assert root_env.subdomain == ""
