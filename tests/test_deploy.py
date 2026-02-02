"""Tests for the deploy command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import click.exceptions
import pytest
from typer.testing import CliRunner

from hostsolo.cli import app
from hostsolo.commands.deploy import (
    deploy_up,
    ensure_app_config,
    ensure_env_files,
    get_app_compose_path,
    logs,
    restart,
    stop,
)


class TestEnsureEnvFiles:
    """Tests for ensure_env_files() function."""

    def test_success_with_all_files(self, project_with_env_files: Path):
        """Test ensure_env_files succeeds when all files exist."""
        # Should not raise
        ensure_env_files("directus", "prod")

    def test_missing_config_directory(self, project_dir: Path):
        """Test ensure_env_files exits when config directory is missing."""
        with pytest.raises(click.exceptions.Exit) as exc_info:
            ensure_env_files("directus", "prod")
        assert exc_info.value.exit_code == 1

    def test_missing_shared_env(self, project_dir: Path):
        """Test ensure_env_files exits when shared.env is missing."""
        config_dir = project_dir / "config" / "directus"
        config_dir.mkdir(parents=True)
        (config_dir / "prod.env").write_text("ENV=prod\n")

        with pytest.raises(click.exceptions.Exit) as exc_info:
            ensure_env_files("directus", "prod")
        assert exc_info.value.exit_code == 1

    def test_missing_env_specific_file(self, project_dir: Path):
        """Test ensure_env_files exits when env-specific file is missing."""
        config_dir = project_dir / "config" / "directus"
        config_dir.mkdir(parents=True)
        (config_dir / "shared.env").write_text("SHARED=value\n")

        with pytest.raises(click.exceptions.Exit) as exc_info:
            ensure_env_files("directus", "prod")
        assert exc_info.value.exit_code == 1


class TestEnsureAppConfig:
    """Tests for ensure_app_config() function."""

    def test_creates_app_directories(self, project_with_env_files: Path):
        """Test ensure_app_config creates app and data directories."""
        compose_path = ensure_app_config("directus", "prod")

        assert compose_path.parent.exists()
        assert (project_with_env_files / "apps" / "prod" / "directus").exists()
        assert (project_with_env_files / "data" / "prod" / "directus").exists()

    def test_renders_compose_file(self, project_with_env_files: Path):
        """Test ensure_app_config renders docker-compose.yml."""
        compose_path = ensure_app_config("directus", "prod")

        assert compose_path.exists()
        content = compose_path.read_text()
        assert "directus" in content
        assert "services:" in content

    def test_custom_tag_override(self, project_with_env_files: Path):
        """Test ensure_app_config uses custom tag."""
        compose_path = ensure_app_config("directus", "prod", tag="11.0.0")

        content = compose_path.read_text()
        assert "11.0.0" in content

    def test_invalid_app_exits(self, project_with_env_files: Path):
        """Test ensure_app_config exits for invalid app."""
        with pytest.raises(click.exceptions.Exit) as exc_info:
            ensure_app_config("nonexistent", "prod")
        assert exc_info.value.exit_code == 1

    def test_invalid_env_exits(self, project_with_env_files: Path):
        """Test ensure_app_config exits for invalid environment."""
        with pytest.raises(click.exceptions.Exit) as exc_info:
            ensure_app_config("directus", "nonexistent")
        assert exc_info.value.exit_code == 1


class TestDeployUp:
    """Tests for deploy up command."""

    def test_deploy_success(
        self, project_with_env_files: Path, runner: CliRunner
    ):
        """Test successful app deployment."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(app, ["deploy", "up", "directus", "--env", "prod"])

        assert result.exit_code == 0
        assert "deployed" in result.stdout
        assert "example.com" in result.stdout

    def test_deploy_with_tag(
        self, project_with_env_files: Path, runner: CliRunner
    ):
        """Test deployment with custom tag."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(
                app, ["deploy", "up", "directus", "--env", "prod", "--tag", "11.0.0"]
            )

        assert result.exit_code == 0
        assert "Tag: 11.0.0" in result.stdout

    def test_deploy_local_mode(
        self, project_with_env_files: Path, runner: CliRunner
    ):
        """Test deployment in local mode."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(app, ["deploy", "up", "directus", "--env", "dev", "--local"])

        assert result.exit_code == 0
        assert "http://" in result.stdout

    def test_deploy_no_pull(
        self, project_with_env_files: Path, runner: CliRunner
    ):
        """Test deployment with --no-pull."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = runner.invoke(
                app, ["deploy", "up", "directus", "--env", "prod", "--no-pull"]
            )

            assert result.exit_code == 0
            # Check that pull command was not called - check actual command args
            for call in mock_run.call_args_list:
                cmd = call[0][0]  # Get the command list
                # Pull command would be ['docker', 'compose', '-f', '...', 'pull']
                assert "pull" not in cmd, f"Unexpected pull command: {cmd}"

    def test_deploy_invalid_app(
        self, project_with_env_files: Path, runner: CliRunner
    ):
        """Test deployment fails for invalid app."""
        result = runner.invoke(app, ["deploy", "up", "nonexistent", "--env", "prod"])

        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_deploy_invalid_env(
        self, project_with_env_files: Path, runner: CliRunner
    ):
        """Test deployment fails for invalid environment."""
        result = runner.invoke(app, ["deploy", "up", "directus", "--env", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_deploy_docker_failure(
        self, project_with_env_files: Path, runner: CliRunner
    ):
        """Test deployment fails when Docker command fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = runner.invoke(app, ["deploy", "up", "directus", "--env", "prod"])

        assert result.exit_code == 1
        assert "Failed" in result.stdout


class TestStop:
    """Tests for stop command via CLI."""

    def test_stop_success(
        self, project_with_deployed_app: Path, runner: CliRunner
    ):
        """Test successful app stop."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(app, ["deploy", "stop", "directus", "--env", "prod"])

        assert result.exit_code == 0
        assert "stopped" in result.stdout

    def test_stop_not_deployed(self, project_dir: Path, runner: CliRunner):
        """Test stop fails when app is not deployed."""
        result = runner.invoke(app, ["deploy", "stop", "directus", "--env", "prod"])

        assert result.exit_code == 1
        assert "not deployed" in result.stdout

    def test_stop_docker_failure(
        self, project_with_deployed_app: Path, runner: CliRunner
    ):
        """Test stop fails when Docker command fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = runner.invoke(app, ["deploy", "stop", "directus", "--env", "prod"])

        assert result.exit_code == 1
        assert "Failed" in result.stdout


class TestLogs:
    """Tests for logs command via CLI."""

    def test_logs_default(
        self, project_with_deployed_app: Path, runner: CliRunner
    ):
        """Test logs command with defaults."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(app, ["deploy", "logs", "directus", "--env", "prod"])

            assert result.exit_code == 0
            call_args = str(mock_run.call_args)
            assert "logs" in call_args
            assert "--tail=100" in call_args

    def test_logs_follow(
        self, project_with_deployed_app: Path, runner: CliRunner
    ):
        """Test logs command with --follow."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(
                app, ["deploy", "logs", "directus", "--env", "prod", "--follow"]
            )

            assert result.exit_code == 0
            call_args = str(mock_run.call_args)
            assert "-f" in call_args

    def test_logs_custom_tail(
        self, project_with_deployed_app: Path, runner: CliRunner
    ):
        """Test logs command with custom --tail."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(
                app, ["deploy", "logs", "directus", "--env", "prod", "--tail", "50"]
            )

            assert result.exit_code == 0
            call_args = str(mock_run.call_args)
            assert "--tail=50" in call_args

    def test_logs_not_deployed(self, project_dir: Path, runner: CliRunner):
        """Test logs fails when app is not deployed."""
        result = runner.invoke(app, ["deploy", "logs", "directus", "--env", "prod"])

        assert result.exit_code == 1
        assert "not deployed" in result.stdout


class TestRestart:
    """Tests for restart command via CLI."""

    def test_restart_success(
        self, project_with_deployed_app: Path, runner: CliRunner
    ):
        """Test successful app restart."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(app, ["deploy", "restart", "directus", "--env", "prod"])

        assert result.exit_code == 0
        assert "restarted" in result.stdout

    def test_restart_not_deployed(self, project_dir: Path, runner: CliRunner):
        """Test restart fails when app is not deployed."""
        result = runner.invoke(app, ["deploy", "restart", "directus", "--env", "prod"])

        assert result.exit_code == 1
        assert "not deployed" in result.stdout

    def test_restart_docker_failure(
        self, project_with_deployed_app: Path, runner: CliRunner
    ):
        """Test restart fails when Docker command fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = runner.invoke(app, ["deploy", "restart", "directus", "--env", "prod"])

        assert result.exit_code == 1
        assert "Failed" in result.stdout
