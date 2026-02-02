"""Tests for the status command."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from hostsolo.cli import app
from hostsolo.commands import status


class TestStatusShow:
    """Tests for the status.show() function."""

    def test_no_config_shows_warning(self, tmp_path: Path, monkeypatch, runner: CliRunner):
        """Test status command when no hostsolo.yaml exists."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 1
        assert "No hostsolo.yaml found" in result.stdout

    def test_no_deployments_shows_empty(
        self, project_dir: Path, runner: CliRunner, mock_subprocess
    ):
        """Test status when no apps are deployed."""
        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "No apps deployed" in result.stdout
        assert "example.com" in result.stdout

    def test_traefik_not_configured(
        self, project_dir: Path, runner: CliRunner, mock_subprocess
    ):
        """Test status shows Traefik as not configured."""
        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "Not configured" in result.stdout

    def test_traefik_running(
        self, project_with_traefik: Path, runner: CliRunner
    ):
        """Test status shows Traefik as running."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='{"Name":"hostsolo-traefik","State":"running"}',
                stderr="",
            )

            result = runner.invoke(app, ["status"])

            assert result.exit_code == 0
            assert "running" in result.stdout

    def test_traefik_stopped(
        self, project_with_traefik: Path, runner: CliRunner
    ):
        """Test status shows Traefik as stopped."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )

            result = runner.invoke(app, ["status"])

            assert result.exit_code == 0
            assert "Not running" in result.stdout

    def test_app_running(
        self, project_with_deployed_app: Path, runner: CliRunner
    ):
        """Test status shows app as running."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='{"Name":"hostsolo-prod-directus","State":"running"}',
                stderr="",
            )

            result = runner.invoke(app, ["status"])

            assert result.exit_code == 0
            assert "directus" in result.stdout
            assert "running" in result.stdout

    def test_app_partial(
        self, project_with_deployed_app: Path, runner: CliRunner
    ):
        """Test status shows app as partial when some containers are not running."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='{"Name":"hostsolo-prod-directus","State":"exited"}',
                stderr="",
            )

            result = runner.invoke(app, ["status"])

            assert result.exit_code == 0
            assert "partial" in result.stdout

    def test_app_stopped(
        self, project_with_deployed_app: Path, runner: CliRunner
    ):
        """Test status shows app as stopped."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )

            result = runner.invoke(app, ["status"])

            assert result.exit_code == 0
            assert "stopped" in result.stdout

    def test_invalid_json_response(
        self, project_with_deployed_app: Path, runner: CliRunner
    ):
        """Test status handles invalid JSON from docker compose ps."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="not valid json",
                stderr="",
            )

            result = runner.invoke(app, ["status"])

            assert result.exit_code == 0
            assert "unknown" in result.stdout

    def test_shows_all_environments(
        self, project_dir: Path, runner: CliRunner, mock_subprocess
    ):
        """Test status shows all configured environments."""
        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "Environments" in result.stdout
        assert "dev" in result.stdout
        assert "staging" in result.stdout
        assert "prod" in result.stdout
