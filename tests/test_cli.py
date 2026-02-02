"""Tests for CLI commands."""

import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hostsolo.cli import app

runner = CliRunner()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_version():
    """Test version command."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "Host Solo v" in result.stdout


def test_init_creates_files(temp_dir, monkeypatch):
    """Test init command creates expected files."""
    monkeypatch.chdir(temp_dir)

    result = runner.invoke(
        app,
        ["init", "--domain", "test.com", "--email", "test@test.com"],
    )

    assert result.exit_code == 0
    assert (temp_dir / "hostsolo.yaml").exists()
    assert (temp_dir / ".env.example").exists()
    assert (temp_dir / "data").exists()
    assert (temp_dir / ".gitignore").exists()

    # Check per-app config directory was created
    assert (temp_dir / "config" / "directus").exists()
    assert (temp_dir / "config" / "directus" / "env.example").exists()


def test_init_creates_gitignore_with_config_exclusions(temp_dir, monkeypatch):
    """Test that .gitignore excludes config env files."""
    monkeypatch.chdir(temp_dir)

    runner.invoke(
        app,
        ["init", "--domain", "test.com", "--email", "test@test.com"],
    )

    gitignore = (temp_dir / ".gitignore").read_text()
    assert "config/*/*.env" in gitignore
    assert "!config/*/env.example" in gitignore


def test_status_without_config(temp_dir, monkeypatch):
    """Test status command without configuration."""
    monkeypatch.chdir(temp_dir)

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 1
    assert "No hostsolo.yaml found" in result.stdout
