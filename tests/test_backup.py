"""Tests for the backup command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import click.exceptions
import pytest
import yaml
from typer.testing import CliRunner

from hostsolo.cli import app
from hostsolo.commands.backup import get_backup_paths, get_backup_provider


class TestGetBackupProvider:
    """Tests for get_backup_provider() function."""

    def test_s3_provider(self, project_dir: Path, mock_env_settings):
        """Test getting S3 provider with valid credentials."""
        with patch("boto3.client") as mock_boto:
            provider = get_backup_provider()
            assert provider is not None
            assert provider.bucket == "test-bucket"

    def test_missing_access_key(self, project_dir: Path, mock_env_settings_missing_s3):
        """Test get_backup_provider exits when access key is missing."""
        with pytest.raises(click.exceptions.Exit) as exc_info:
            get_backup_provider()
        assert exc_info.value.exit_code == 1

    def test_missing_secret_key(self, project_dir: Path):
        """Test get_backup_provider exits when secret key is missing."""
        from hostsolo.config import EnvironmentSettings

        settings = EnvironmentSettings(
            aws_access_key_id="AKIA...",
            aws_secret_access_key=None,
        )
        with patch("hostsolo.commands.backup.load_env_settings", return_value=settings):
            with pytest.raises(click.exceptions.Exit) as exc_info:
                get_backup_provider()
            assert exc_info.value.exit_code == 1

    def test_unknown_provider(self, project_dir: Path, mock_env_settings):
        """Test get_backup_provider exits for unknown provider."""
        config_path = project_dir / "hostsolo.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)
        config["backup"]["provider"] = "unknown"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        with pytest.raises(click.exceptions.Exit) as exc_info:
            get_backup_provider()
        assert exc_info.value.exit_code == 1

    def test_with_endpoint_url(self, project_dir: Path, mock_env_settings):
        """Test S3 provider with custom endpoint URL."""
        config_path = project_dir / "hostsolo.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)
        config["backup"]["endpoint_url"] = "https://s3.custom.com"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        with patch("boto3.client") as mock_boto:
            provider = get_backup_provider()
            assert provider is not None


class TestGetBackupPaths:
    """Tests for get_backup_paths() function."""

    def test_existing_paths(self, project_dir: Path):
        """Test get_backup_paths returns existing paths."""
        # Create data directory
        data_dir = project_dir / "data" / "prod" / "directus"
        data_dir.mkdir(parents=True, exist_ok=True)

        paths = get_backup_paths("directus", "prod")

        assert len(paths) == 1
        assert paths[0] == data_dir

    def test_env_replacement(self, project_dir: Path):
        """Test ${ENV} is replaced in backup paths."""
        # Create data directories for different envs
        prod_dir = project_dir / "data" / "prod" / "directus"
        dev_dir = project_dir / "data" / "dev" / "directus"
        prod_dir.mkdir(parents=True, exist_ok=True)
        dev_dir.mkdir(parents=True, exist_ok=True)

        prod_paths = get_backup_paths("directus", "prod")
        dev_paths = get_backup_paths("directus", "dev")

        assert prod_dir in prod_paths
        assert dev_dir in dev_paths

    def test_missing_app(self, project_dir: Path):
        """Test get_backup_paths exits for missing app."""
        with pytest.raises(click.exceptions.Exit) as exc_info:
            get_backup_paths("nonexistent", "prod")
        assert exc_info.value.exit_code == 1

    def test_nonexistent_path_warning(self, project_dir: Path, capsys):
        """Test get_backup_paths warns about nonexistent paths."""
        # Don't create the data directory
        paths = get_backup_paths("directus", "prod")

        assert len(paths) == 0
        # Warning should have been printed
        captured = capsys.readouterr()
        assert "does not exist" in captured.out


class TestBackupNow:
    """Tests for backup now command."""

    def test_backup_success(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test successful backup."""
        # Create data directory
        data_dir = project_dir / "data" / "prod" / "directus"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "test.db").write_text("data")

        with patch("hostsolo.commands.backup.get_backup_provider") as mock_provider:
            mock_backup = MagicMock()
            mock_provider.return_value = mock_backup

            result = runner.invoke(
                app, ["backup", "now", "directus", "--env", "prod"]
            )

            assert result.exit_code == 0
            assert "Backup complete" in result.stdout
            mock_backup.upload_directory.assert_called()

    def test_backup_no_paths(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test backup fails when no backup paths exist."""
        # Use myapp which has no backup_paths
        with patch("hostsolo.commands.backup.get_backup_provider") as mock_provider:
            mock_provider.return_value = MagicMock()
            result = runner.invoke(app, ["backup", "now", "myapp", "--env", "prod"])

        assert result.exit_code == 1
        assert "No backup paths" in result.stdout

    def test_backup_upload_failure(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test backup handles upload failure."""
        data_dir = project_dir / "data" / "prod" / "directus"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "test.db").write_text("data")

        with patch("hostsolo.commands.backup.get_backup_provider") as mock_provider:
            mock_backup = MagicMock()
            mock_backup.upload_directory.side_effect = Exception("Upload failed")
            mock_provider.return_value = mock_backup

            result = runner.invoke(
                app, ["backup", "now", "directus", "--env", "prod"]
            )

            assert result.exit_code == 1
            assert "Failed to backup" in result.stdout


class TestBackupList:
    """Tests for backup list command."""

    def test_list_success(
        self, project_dir: Path, runner: CliRunner, mock_env_settings, sample_backup_list
    ):
        """Test listing backups."""
        with patch("hostsolo.commands.backup.get_backup_provider") as mock_provider:
            mock_backup = MagicMock()
            mock_backup.list_backups.return_value = sample_backup_list
            mock_provider.return_value = mock_backup

            result = runner.invoke(
                app, ["backup", "list", "directus", "--env", "prod"]
            )

            assert result.exit_code == 0
            assert "2024-01-01" in result.stdout

    def test_list_empty(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test listing backups when none exist."""
        with patch("hostsolo.commands.backup.get_backup_provider") as mock_provider:
            mock_backup = MagicMock()
            mock_backup.list_backups.return_value = []
            mock_provider.return_value = mock_backup

            result = runner.invoke(
                app, ["backup", "list", "directus", "--env", "prod"]
            )

            assert result.exit_code == 0
            assert "No backups found" in result.stdout

    def test_list_with_limit(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test listing backups with --limit."""
        with patch("hostsolo.commands.backup.get_backup_provider") as mock_provider:
            mock_backup = MagicMock()
            # Return many backups
            backups = [f"prod/directus/2024-01-0{i}T12-00-00/data.db" for i in range(1, 10)]
            mock_backup.list_backups.return_value = backups
            mock_provider.return_value = mock_backup

            result = runner.invoke(
                app, ["backup", "list", "directus", "--env", "prod", "--limit", "5"]
            )

            assert result.exit_code == 0

    def test_list_api_failure(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test list handles API failure."""
        with patch("hostsolo.commands.backup.get_backup_provider") as mock_provider:
            mock_backup = MagicMock()
            mock_backup.list_backups.side_effect = Exception("API Error")
            mock_provider.return_value = mock_backup

            result = runner.invoke(
                app, ["backup", "list", "directus", "--env", "prod"]
            )

            assert result.exit_code == 1
            assert "Failed to list backups" in result.stdout


class TestBackupRestore:
    """Tests for backup restore command."""

    def test_restore_with_force(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test restoring backup with --force."""
        data_dir = project_dir / "data" / "prod" / "directus"
        data_dir.mkdir(parents=True, exist_ok=True)

        with patch("hostsolo.commands.backup.get_backup_provider") as mock_provider:
            mock_backup = MagicMock()
            mock_provider.return_value = mock_backup

            result = runner.invoke(
                app,
                [
                    "backup",
                    "restore",
                    "directus",
                    "--env",
                    "prod",
                    "--timestamp",
                    "2024-01-01T12-00-00",
                    "--force",
                ],
            )

            assert result.exit_code == 0
            assert "Restore complete" in result.stdout
            mock_backup.download_directory.assert_called()

    def test_restore_with_confirmation(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test restoring backup with confirmation."""
        data_dir = project_dir / "data" / "prod" / "directus"
        data_dir.mkdir(parents=True, exist_ok=True)

        with patch("hostsolo.commands.backup.get_backup_provider") as mock_provider:
            mock_backup = MagicMock()
            mock_provider.return_value = mock_backup

            result = runner.invoke(
                app,
                [
                    "backup",
                    "restore",
                    "directus",
                    "--env",
                    "prod",
                    "--timestamp",
                    "2024-01-01T12-00-00",
                ],
                input="y\n",
            )

            assert result.exit_code == 0
            mock_backup.download_directory.assert_called()

    def test_restore_cancelled(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test cancelling backup restore."""
        data_dir = project_dir / "data" / "prod" / "directus"
        data_dir.mkdir(parents=True, exist_ok=True)

        with patch("hostsolo.commands.backup.get_backup_provider") as mock_provider:
            mock_backup = MagicMock()
            mock_provider.return_value = mock_backup

            result = runner.invoke(
                app,
                [
                    "backup",
                    "restore",
                    "directus",
                    "--env",
                    "prod",
                    "--timestamp",
                    "2024-01-01T12-00-00",
                ],
                input="n\n",
            )

            assert "Aborted" in result.stdout or result.exit_code == 1
            mock_backup.download_directory.assert_not_called()

    def test_restore_download_failure(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test restore handles download failure."""
        data_dir = project_dir / "data" / "prod" / "directus"
        data_dir.mkdir(parents=True, exist_ok=True)

        with patch("hostsolo.commands.backup.get_backup_provider") as mock_provider:
            mock_backup = MagicMock()
            mock_backup.download_directory.side_effect = Exception("Download failed")
            mock_provider.return_value = mock_backup

            result = runner.invoke(
                app,
                [
                    "backup",
                    "restore",
                    "directus",
                    "--env",
                    "prod",
                    "--timestamp",
                    "2024-01-01T12-00-00",
                    "--force",
                ],
            )

            assert result.exit_code == 1
            assert "Failed to restore" in result.stdout


class TestBackupDelete:
    """Tests for backup delete command."""

    def test_delete_with_force(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test deleting backup with --force."""
        with patch("hostsolo.commands.backup.get_backup_provider") as mock_provider:
            mock_backup = MagicMock()
            mock_provider.return_value = mock_backup

            result = runner.invoke(
                app,
                [
                    "backup",
                    "delete",
                    "directus",
                    "--env",
                    "prod",
                    "--timestamp",
                    "2024-01-01T12-00-00",
                    "--force",
                ],
            )

            assert result.exit_code == 0
            assert "Backup deleted" in result.stdout
            mock_backup.delete_backup.assert_called_once()

    def test_delete_with_confirmation(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test deleting backup with confirmation."""
        with patch("hostsolo.commands.backup.get_backup_provider") as mock_provider:
            mock_backup = MagicMock()
            mock_provider.return_value = mock_backup

            result = runner.invoke(
                app,
                [
                    "backup",
                    "delete",
                    "directus",
                    "--env",
                    "prod",
                    "--timestamp",
                    "2024-01-01T12-00-00",
                ],
                input="y\n",
            )

            assert result.exit_code == 0
            mock_backup.delete_backup.assert_called_once()

    def test_delete_api_failure(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test delete handles API failure."""
        with patch("hostsolo.commands.backup.get_backup_provider") as mock_provider:
            mock_backup = MagicMock()
            mock_backup.delete_backup.side_effect = Exception("API Error")
            mock_provider.return_value = mock_backup

            result = runner.invoke(
                app,
                [
                    "backup",
                    "delete",
                    "directus",
                    "--env",
                    "prod",
                    "--timestamp",
                    "2024-01-01T12-00-00",
                    "--force",
                ],
            )

            assert result.exit_code == 1
            assert "Failed to delete backup" in result.stdout
