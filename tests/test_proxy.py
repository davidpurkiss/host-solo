"""Tests for the proxy command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from hostsolo.cli import app
from hostsolo.commands.proxy import ensure_traefik_config, get_traefik_compose_path


class TestEnsureTraefikConfig:
    """Tests for ensure_traefik_config() function."""

    def test_creates_traefik_directory(self, project_dir: Path):
        """Test ensure_traefik_config creates traefik directory."""
        ensure_traefik_config(local=False)

        traefik_dir = project_dir / "traefik"
        assert traefik_dir.exists()

    def test_renders_compose_file(self, project_dir: Path):
        """Test ensure_traefik_config renders docker-compose.yml."""
        ensure_traefik_config(local=False)

        compose_path = project_dir / "traefik" / "docker-compose.yml"
        assert compose_path.exists()
        content = compose_path.read_text()
        assert "traefik" in content
        assert "services:" in content

    def test_creates_acme_json(self, project_dir: Path):
        """Test ensure_traefik_config creates acme.json with correct permissions."""
        ensure_traefik_config(local=False)

        acme_path = project_dir / "traefik" / "acme.json"
        assert acme_path.exists()
        # Check permissions are 600
        assert oct(acme_path.stat().st_mode)[-3:] == "600"

    def test_creates_dynamic_directory(self, project_dir: Path):
        """Test ensure_traefik_config creates dynamic config directory."""
        ensure_traefik_config(local=False)

        dynamic_dir = project_dir / "traefik" / "dynamic"
        assert dynamic_dir.exists()

    def test_local_mode(self, project_dir: Path):
        """Test ensure_traefik_config in local mode."""
        ensure_traefik_config(local=True)

        compose_path = project_dir / "traefik" / "docker-compose.yml"
        content = compose_path.read_text()
        # Local mode should enable dashboard
        assert "8080" in content or "dashboard" in content


class TestProxyUp:
    """Tests for proxy up command."""

    def test_up_success(
        self, project_dir: Path, runner: CliRunner, mock_docker_success
    ):
        """Test successful proxy start."""
        result = runner.invoke(app, ["proxy", "up"])

        assert result.exit_code == 0
        assert "Traefik started" in result.stdout
        assert mock_docker_success.called

    def test_up_local_mode(
        self, project_dir: Path, runner: CliRunner, mock_docker_success
    ):
        """Test proxy start in local mode."""
        result = runner.invoke(app, ["proxy", "up", "--local"])

        assert result.exit_code == 0
        assert "local mode" in result.stdout
        assert "Dashboard: http://localhost:8080" in result.stdout

    def test_up_no_detach(self, project_dir: Path, runner: CliRunner):
        """Test proxy start without detach."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = runner.invoke(app, ["proxy", "up", "--no-detach"])

            assert result.exit_code == 0
            # Verify -d flag not in command
            call_args = str(mock_run.call_args)
            # Check if '-d' appears as a standalone argument
            args_list = mock_run.call_args[0][0] if mock_run.call_args[0] else []
            assert "-d" not in args_list

    def test_up_docker_failure(
        self, project_dir: Path, runner: CliRunner, mock_docker_failure
    ):
        """Test proxy start fails when Docker command fails."""
        result = runner.invoke(app, ["proxy", "up"])

        assert result.exit_code == 1
        assert "Failed to start Traefik" in result.stdout


class TestProxyDown:
    """Tests for proxy down command."""

    def test_down_success(
        self, project_with_traefik: Path, runner: CliRunner, mock_docker_success
    ):
        """Test successful proxy stop."""
        result = runner.invoke(app, ["proxy", "down"])

        assert result.exit_code == 0
        assert "Traefik stopped" in result.stdout

    def test_down_not_configured(self, project_dir: Path, runner: CliRunner):
        """Test proxy down fails when not configured."""
        # Remove traefik directory if exists
        traefik_dir = project_dir / "traefik"
        if traefik_dir.exists():
            import shutil
            shutil.rmtree(traefik_dir)

        result = runner.invoke(app, ["proxy", "down"])

        assert result.exit_code == 1
        assert "not configured" in result.stdout

    def test_down_docker_failure(
        self, project_with_traefik: Path, runner: CliRunner, mock_docker_failure
    ):
        """Test proxy down fails when Docker command fails."""
        result = runner.invoke(app, ["proxy", "down"])

        assert result.exit_code == 1
        assert "Failed to stop Traefik" in result.stdout


class TestProxyLogs:
    """Tests for proxy logs command."""

    def test_logs_default(
        self, project_with_traefik: Path, runner: CliRunner, mock_docker_success
    ):
        """Test logs command with defaults."""
        result = runner.invoke(app, ["proxy", "logs"])

        assert result.exit_code == 0
        call_args = str(mock_docker_success.call_args)
        assert "logs" in call_args
        assert "--tail=100" in call_args

    def test_logs_follow(
        self, project_with_traefik: Path, runner: CliRunner, mock_docker_success
    ):
        """Test logs command with --follow."""
        result = runner.invoke(app, ["proxy", "logs", "--follow"])

        assert result.exit_code == 0
        call_args = str(mock_docker_success.call_args)
        assert "-f" in call_args

    def test_logs_not_configured(self, project_dir: Path, runner: CliRunner):
        """Test logs fails when not configured."""
        traefik_dir = project_dir / "traefik"
        if traefik_dir.exists():
            import shutil
            shutil.rmtree(traefik_dir)

        result = runner.invoke(app, ["proxy", "logs"])

        assert result.exit_code == 1
        assert "not configured" in result.stdout


class TestProxyRestart:
    """Tests for proxy restart command."""

    def test_restart_success(
        self, project_with_traefik: Path, runner: CliRunner, mock_docker_success
    ):
        """Test successful proxy restart."""
        result = runner.invoke(app, ["proxy", "restart"])

        assert result.exit_code == 0
        assert "Traefik restarted" in result.stdout

    def test_restart_not_configured(self, project_dir: Path, runner: CliRunner):
        """Test restart fails when not configured."""
        traefik_dir = project_dir / "traefik"
        if traefik_dir.exists():
            import shutil
            shutil.rmtree(traefik_dir)

        result = runner.invoke(app, ["proxy", "restart"])

        assert result.exit_code == 1
        assert "not configured" in result.stdout

    def test_restart_docker_failure(
        self, project_with_traefik: Path, runner: CliRunner, mock_docker_failure
    ):
        """Test restart fails when Docker command fails."""
        result = runner.invoke(app, ["proxy", "restart"])

        assert result.exit_code == 1
        assert "Failed to restart Traefik" in result.stdout
