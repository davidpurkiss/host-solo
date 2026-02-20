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

    assert "data/staging/directus" in content
    assert "${ENV}" not in content


def test_multiline_env_value_uses_literal_block(sample_config, tmp_path, monkeypatch):
    """Test multiline environment values render as YAML literal blocks."""
    config_file = tmp_path / "hostsolo.yaml"
    config_file.write_text(yaml.dump({"domain": "example.com", "email": "test@test.com"}))
    monkeypatch.chdir(tmp_path)

    app_config = AppConfig(
        image="myapp/myapp",
        tag="latest",
        ports=["3000"],
        environment={"MULTI": "line1\nline2\nline3"},
    )

    content = render_app_compose(
        config=sample_config,
        app_name="myapp",
        app_config=app_config,
        env_name="prod",
        domain="example.com",
    )

    # Should use literal block style, not double-quoted with raw newlines
    assert "MULTI: |-" in content
    assert "        line1" in content
    assert "        line2" in content
    assert "        line3" in content

    # Verify the output is valid YAML that preserves the multiline value
    parsed = yaml.safe_load(content)
    assert parsed["services"]["myapp"]["environment"]["MULTI"] == "line1\nline2\nline3"


def test_single_line_env_value_uses_quotes(sample_config, tmp_path, monkeypatch):
    """Test single-line environment values are double-quoted."""
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
    )

    assert 'DB_CLIENT: "sqlite3"' in content


def test_env_var_interpolation(sample_config, tmp_path, monkeypatch):
    """Test ${VAR} in environment values are resolved from env files."""
    config_file = tmp_path / "hostsolo.yaml"
    config_file.write_text(yaml.dump({"domain": "example.com", "email": "test@test.com"}))
    monkeypatch.chdir(tmp_path)

    # Create env files with variables
    config_dir = tmp_path / "config" / "myapp"
    config_dir.mkdir(parents=True)
    (config_dir / "shared.env").write_text("DB_HOST=localhost\nDB_PORT=5432\n")
    (config_dir / "prod.env").write_text("DB_NAME=mydb_prod\n")

    app_config = AppConfig(
        image="myapp/myapp",
        tag="latest",
        ports=["3000"],
        environment={
            "DATABASE_URL": "postgres://${DB_HOST}:${DB_PORT}/${DB_NAME}",
        },
    )

    content = render_app_compose(
        config=sample_config,
        app_name="myapp",
        app_config=app_config,
        env_name="prod",
        domain="example.com",
    )

    assert "postgres://localhost:5432/mydb_prod" in content


def test_unresolved_env_var_kept(sample_config, tmp_path, monkeypatch):
    """Test unresolved ${VAR} references are left as-is."""
    config_file = tmp_path / "hostsolo.yaml"
    config_file.write_text(yaml.dump({"domain": "example.com", "email": "test@test.com"}))
    monkeypatch.chdir(tmp_path)

    # Create minimal env files (no UNDEFINED var)
    config_dir = tmp_path / "config" / "myapp"
    config_dir.mkdir(parents=True)
    (config_dir / "shared.env").write_text("")
    (config_dir / "prod.env").write_text("")

    app_config = AppConfig(
        image="myapp/myapp",
        tag="latest",
        ports=["3000"],
        environment={"MISSING": "${UNDEFINED}"},
    )

    content = render_app_compose(
        config=sample_config,
        app_name="myapp",
        app_config=app_config,
        env_name="prod",
        domain="example.com",
    )

    assert "${UNDEFINED}" in content
