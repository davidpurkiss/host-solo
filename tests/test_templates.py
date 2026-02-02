"""Tests for template rendering."""

import tempfile
from pathlib import Path

import pytest
import yaml

from hostsolo.config import AppConfig, HostSoloConfig, load_config
from hostsolo.templates import render_app_compose, render_traefik_compose


@pytest.fixture
def sample_config():
    """Create a sample configuration."""
    return HostSoloConfig(
        domain="example.com",
        email="admin@example.com",
        environments={
            "dev": {"subdomain": "dev"},
            "prod": {"subdomain": ""},
        },
        apps={
            "directus": {
                "image": "directus/directus",
                "tag": "10.10.5",
                "ports": ["8055"],
                "volumes": ["./data/${ENV}/directus:/directus/database"],
                "environment": {"DB_CLIENT": "sqlite3"},
            }
        },
    )


def test_render_traefik_compose(sample_config):
    """Test Traefik compose template rendering."""
    content = render_traefik_compose(sample_config, local=False)

    assert "traefik:" in content
    assert "hostsolo-traefik" in content
    assert "letsencrypt" in content
    assert sample_config.email in content


def test_render_traefik_compose_local(sample_config):
    """Test Traefik compose in local mode."""
    content = render_traefik_compose(sample_config, local=True)

    assert "traefik:" in content
    assert "8080:8080" in content  # Dashboard port
    assert "api.dashboard=true" in content


def test_render_app_compose(sample_config, tmp_path, monkeypatch):
    """Test app compose template rendering."""
    # Create a temporary hostsolo.yaml so get_project_root works
    config_file = tmp_path / "hostsolo.yaml"
    config_file.write_text(yaml.dump({"domain": "example.com", "email": "test@test.com"}))
    monkeypatch.chdir(tmp_path)

    app_config = sample_config.apps["directus"]

    content = render_app_compose(
        config=sample_config,
        app_name="directus",
        app_config=app_config,
        env_name="prod",
        domain="example.com",
        local=False,
    )

    assert "directus:" in content
    assert "hostsolo-prod-directus" in content
    assert "example.com" in content
    assert "tls.certresolver=letsencrypt" in content
    assert "env_file:" in content
    assert "shared.env" in content
    assert "prod.env" in content


def test_render_app_compose_local(sample_config, tmp_path, monkeypatch):
    """Test app compose in local mode."""
    config_file = tmp_path / "hostsolo.yaml"
    config_file.write_text(yaml.dump({"domain": "example.com", "email": "test@test.com"}))
    monkeypatch.chdir(tmp_path)

    app_config = sample_config.apps["directus"]

    content = render_app_compose(
        config=sample_config,
        app_name="directus",
        app_config=app_config,
        env_name="dev",
        domain="dev.example.com",
        local=True,
    )

    assert "directus:" in content
    assert "hostsolo-dev-directus" in content
    assert "entrypoints=web" in content
    assert "tls" not in content.lower() or "tls=true" not in content


def test_volume_env_replacement(sample_config, tmp_path, monkeypatch):
    """Test that ${ENV} is replaced in volume paths."""
    config_file = tmp_path / "hostsolo.yaml"
    config_file.write_text(yaml.dump({"domain": "example.com", "email": "test@test.com"}))
    monkeypatch.chdir(tmp_path)

    app_config = sample_config.apps["directus"]

    content = render_app_compose(
        config=sample_config,
        app_name="directus",
        app_config=app_config,
        env_name="staging",
        domain="staging.example.com",
        local=False,
    )

    assert "./data/staging/directus" in content
    assert "${ENV}" not in content
