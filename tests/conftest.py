"""Shared test fixtures for Host Solo tests."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from hostsolo.config import (
    AppConfig,
    BackupConfig,
    DNSConfig,
    EnvironmentConfig,
    EnvironmentSettings,
    HostSoloConfig,
)


# ============================================================================
# CLI Fixtures
# ============================================================================


@pytest.fixture
def runner() -> CliRunner:
    """Provide a Typer CLI test runner."""
    return CliRunner()


# ============================================================================
# Project Directory Fixtures
# ============================================================================


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch) -> Path:
    """Create a temporary project directory with hostsolo.yaml."""
    config_data = {
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
            },
            "myapp": {
                "image": "myapp/myapp",
                "tag": "latest",
                "ports": ["3000"],
                "volumes": [],
                "environment": {},
                "backup_paths": [],
            },
        },
    }

    config_file = tmp_path / "hostsolo.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    # Create directory structure
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "apps").mkdir(exist_ok=True)
    (tmp_path / "traefik").mkdir(exist_ok=True)

    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def project_with_env_files(project_dir: Path) -> Path:
    """Create a project with config/{app}/*.env files."""
    # Create config directories for each app
    for app_name in ["directus", "myapp"]:
        config_dir = project_dir / "config" / app_name
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create shared.env
        (config_dir / "shared.env").write_text("SHARED_VAR=value\n")

        # Create environment-specific files
        for env in ["dev", "staging", "prod"]:
            (config_dir / f"{env}.env").write_text(f"ENV_NAME={env}\n")

        # Create env.example
        (config_dir / "env.example").write_text("EXAMPLE_VAR=example\n")

    return project_dir


@pytest.fixture
def project_with_traefik(project_dir: Path) -> Path:
    """Create a project with Traefik configured."""
    traefik_dir = project_dir / "traefik"
    traefik_dir.mkdir(exist_ok=True)

    compose_content = """
services:
  traefik:
    image: traefik:v3.0
    container_name: hostsolo-traefik
"""
    (traefik_dir / "docker-compose.yml").write_text(compose_content)

    return project_dir


@pytest.fixture
def project_with_deployed_app(project_with_env_files: Path) -> Path:
    """Create a project with a deployed app."""
    project_dir = project_with_env_files

    # Create app directory structure
    app_dir = project_dir / "apps" / "prod" / "directus"
    app_dir.mkdir(parents=True, exist_ok=True)

    compose_content = """
services:
  directus:
    image: directus/directus:10.10.5
    container_name: hostsolo-prod-directus
"""
    (app_dir / "docker-compose.yml").write_text(compose_content)

    # Create data directory
    data_dir = project_dir / "data" / "prod" / "directus"
    data_dir.mkdir(parents=True, exist_ok=True)

    return project_dir


# ============================================================================
# Mock Fixtures - Subprocess
# ============================================================================


@pytest.fixture
def mock_subprocess():
    """Mock subprocess.run for Docker commands."""
    with patch("subprocess.run") as mock:
        mock.return_value = MagicMock(returncode=0, stdout="", stderr="")
        yield mock


@pytest.fixture
def mock_docker_success(mock_subprocess):
    """Configure subprocess mock for successful Docker commands."""
    mock_subprocess.return_value = MagicMock(returncode=0, stdout="", stderr="")
    return mock_subprocess


@pytest.fixture
def mock_docker_failure(mock_subprocess):
    """Configure subprocess mock for failed Docker commands."""
    mock_subprocess.return_value = MagicMock(returncode=1, stdout="", stderr="Error")
    return mock_subprocess


@pytest.fixture
def mock_docker_ps_running():
    """Mock docker compose ps with running containers."""
    with patch("subprocess.run") as mock:
        mock.return_value = MagicMock(
            returncode=0,
            stdout='{"Name":"test","State":"running"}',
            stderr="",
        )
        yield mock


@pytest.fixture
def mock_docker_ps_stopped():
    """Mock docker compose ps with no running containers."""
    with patch("subprocess.run") as mock:
        mock.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )
        yield mock


# ============================================================================
# Mock Fixtures - HTTP/API
# ============================================================================


@pytest.fixture
def mock_httpx_get():
    """Mock httpx.get for IP detection and API calls."""
    with patch("httpx.get") as mock:
        mock.return_value = MagicMock(status_code=200, text="192.168.1.100")
        yield mock


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.Client for API calls."""
    with patch("httpx.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        yield mock_client


# ============================================================================
# Mock Fixtures - boto3/S3
# ============================================================================


@pytest.fixture
def mock_boto3():
    """Mock boto3.client for S3 operations."""
    with patch("boto3.client") as mock_client_func:
        mock_client = MagicMock()
        mock_client_func.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_boto3_with_backups(mock_boto3):
    """Mock boto3 with backup listing response."""
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {
            "Contents": [
                {"Key": "prod/directus/2024-01-01T12-00-00/data.db"},
                {"Key": "prod/directus/2024-01-01T12-00-00/uploads/file.jpg"},
                {"Key": "prod/directus/2024-01-02T12-00-00/data.db"},
            ]
        }
    ]
    mock_boto3.get_paginator.return_value = paginator
    return mock_boto3


# ============================================================================
# Mock Fixtures - Environment Settings
# ============================================================================


@pytest.fixture
def mock_env_settings():
    """Mock environment settings with test credentials."""
    settings = EnvironmentSettings(
        dnsimple_token="test-token",
        dnsimple_account_id="12345",
        aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
        aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        aws_region="us-east-1",
    )
    # Patch in multiple modules where load_env_settings is imported
    with patch("hostsolo.config.load_env_settings", return_value=settings):
        with patch("hostsolo.commands.dns.load_env_settings", return_value=settings):
            with patch("hostsolo.commands.backup.load_env_settings", return_value=settings):
                yield settings


@pytest.fixture
def mock_env_settings_missing_dns():
    """Mock environment settings without DNS credentials."""
    settings = EnvironmentSettings(
        dnsimple_token=None,
        dnsimple_account_id=None,
    )
    with patch("hostsolo.config.load_env_settings", return_value=settings):
        with patch("hostsolo.commands.dns.load_env_settings", return_value=settings):
            with patch("hostsolo.commands.backup.load_env_settings", return_value=settings):
                yield settings


@pytest.fixture
def mock_env_settings_missing_s3():
    """Mock environment settings without S3 credentials."""
    settings = EnvironmentSettings(
        aws_access_key_id=None,
        aws_secret_access_key=None,
    )
    with patch("hostsolo.config.load_env_settings", return_value=settings):
        with patch("hostsolo.commands.dns.load_env_settings", return_value=settings):
            with patch("hostsolo.commands.backup.load_env_settings", return_value=settings):
                yield settings


# ============================================================================
# Sample Data Fixtures
# ============================================================================


@pytest.fixture
def sample_config() -> HostSoloConfig:
    """Provide a sample HostSoloConfig instance."""
    return HostSoloConfig(
        domain="example.com",
        email="admin@example.com",
        data_dir="./data",
        dns=DNSConfig(provider="dnsimple"),
        backup=BackupConfig(
            provider="s3",
            bucket="test-bucket",
            schedule="0 */6 * * *",
        ),
        environments={
            "dev": EnvironmentConfig(subdomain="dev"),
            "staging": EnvironmentConfig(subdomain="staging"),
            "prod": EnvironmentConfig(subdomain=""),
        },
        apps={
            "directus": AppConfig(
                image="directus/directus",
                tag="10.10.5",
                ports=["8055"],
                volumes=["./data/${ENV}/directus:/directus/database"],
                environment={"DB_CLIENT": "sqlite3"},
                backup_paths=["./data/${ENV}/directus"],
            ),
        },
    )


@pytest.fixture
def sample_dns_records() -> list[dict]:
    """Provide sample DNS record data."""
    return [
        {
            "id": 1,
            "type": "A",
            "name": "@",
            "content": "192.168.1.100",
            "ttl": 3600,
        },
        {
            "id": 2,
            "type": "A",
            "name": "dev",
            "content": "192.168.1.100",
            "ttl": 3600,
        },
        {
            "id": 3,
            "type": "CNAME",
            "name": "www",
            "content": "example.com",
            "ttl": 3600,
        },
    ]


@pytest.fixture
def sample_backup_list() -> list[str]:
    """Provide sample backup keys."""
    return [
        "prod/directus/2024-01-01T12-00-00/data.db",
        "prod/directus/2024-01-01T12-00-00/uploads/file.jpg",
        "prod/directus/2024-01-02T12-00-00/data.db",
        "prod/directus/2024-01-02T12-00-00/uploads/file.jpg",
    ]
