"""Tests for the env command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from hostsolo.cli import app


class TestListEnvs:
    """Tests for env list command."""

    def test_list_success(self, project_dir: Path, runner: CliRunner):
        """Test listing environments."""
        result = runner.invoke(app, ["env", "list"])

        assert result.exit_code == 0
        assert "Environment" in result.stdout
        assert "Subdomain" in result.stdout
        assert "Full Domain" in result.stdout

    def test_shows_all_envs(self, project_dir: Path, runner: CliRunner):
        """Test list shows all configured environments."""
        result = runner.invoke(app, ["env", "list"])

        assert result.exit_code == 0
        assert "dev" in result.stdout
        assert "staging" in result.stdout
        assert "prod" in result.stdout

    def test_shows_domains(self, project_dir: Path, runner: CliRunner):
        """Test list shows full domain for each env."""
        result = runner.invoke(app, ["env", "list"])

        assert result.exit_code == 0
        assert "dev.example.com" in result.stdout
        assert "staging.example.com" in result.stdout
        assert "example.com" in result.stdout  # prod root domain


class TestCreateEnv:
    """Tests for env create command."""

    def test_create_success(self, project_dir: Path, runner: CliRunner):
        """Test creating a new environment."""
        result = runner.invoke(app, ["env", "create", "test"])

        assert result.exit_code == 0
        assert "Created environment: test" in result.stdout

        # Verify config was updated
        with open(project_dir / "hostsolo.yaml") as f:
            config = yaml.safe_load(f)
        assert "test" in config["environments"]
        assert config["environments"]["test"]["subdomain"] == "test"

    def test_create_with_subdomain(self, project_dir: Path, runner: CliRunner):
        """Test creating environment with custom subdomain."""
        result = runner.invoke(
            app, ["env", "create", "test", "--subdomain", "custom-sub"]
        )

        assert result.exit_code == 0
        assert "custom-sub" in result.stdout

        with open(project_dir / "hostsolo.yaml") as f:
            config = yaml.safe_load(f)
        assert config["environments"]["test"]["subdomain"] == "custom-sub"

    def test_create_default_subdomain(self, project_dir: Path, runner: CliRunner):
        """Test creating environment uses name as default subdomain."""
        result = runner.invoke(app, ["env", "create", "feature"])

        assert result.exit_code == 0

        with open(project_dir / "hostsolo.yaml") as f:
            config = yaml.safe_load(f)
        assert config["environments"]["feature"]["subdomain"] == "feature"

    def test_create_already_exists(self, project_dir: Path, runner: CliRunner):
        """Test create fails when environment already exists."""
        result = runner.invoke(app, ["env", "create", "prod"])

        assert result.exit_code == 1
        assert "already exists" in result.stdout

    def test_create_no_config(self, tmp_path: Path, monkeypatch, runner: CliRunner):
        """Test create fails when no config file exists."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["env", "create", "test"])

        assert result.exit_code == 1
        assert "No hostsolo.yaml found" in result.stdout


class TestDestroyEnv:
    """Tests for env destroy command."""

    def test_destroy_success(
        self, project_with_deployed_app: Path, runner: CliRunner, mock_docker_success
    ):
        """Test successful environment destruction."""
        # Create dev environment with apps
        dev_app_dir = project_with_deployed_app / "apps" / "dev" / "directus"
        dev_app_dir.mkdir(parents=True, exist_ok=True)
        (dev_app_dir / "docker-compose.yml").write_text("services:\n  test:\n")

        result = runner.invoke(app, ["env", "destroy", "dev"])

        assert result.exit_code == 0
        assert "destroyed" in result.stdout

    def test_destroy_stops_containers(
        self, project_with_deployed_app: Path, runner: CliRunner
    ):
        """Test destroy stops running containers."""
        # Create environment with deployed app
        app_dir = project_with_deployed_app / "apps" / "dev" / "directus"
        app_dir.mkdir(parents=True, exist_ok=True)
        (app_dir / "docker-compose.yml").write_text("services:\n  test:\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = runner.invoke(app, ["env", "destroy", "dev"])

            assert result.exit_code == 0
            # Verify docker compose down was called
            call_args = [str(call) for call in mock_run.call_args_list]
            assert any("down" in str(c) for c in call_args)

    def test_destroy_removes_configs(
        self, project_with_deployed_app: Path, runner: CliRunner, mock_docker_success
    ):
        """Test destroy removes app configurations."""
        # Create dev environment
        dev_app_dir = project_with_deployed_app / "apps" / "dev"
        dev_app_dir.mkdir(parents=True, exist_ok=True)
        (dev_app_dir / "directus" / "docker-compose.yml").parent.mkdir(
            parents=True, exist_ok=True
        )
        (dev_app_dir / "directus" / "docker-compose.yml").write_text("services:\n")

        result = runner.invoke(app, ["env", "destroy", "dev"])

        assert result.exit_code == 0
        assert not dev_app_dir.exists()

    def test_destroy_with_data(
        self, project_with_deployed_app: Path, runner: CliRunner, mock_docker_success
    ):
        """Test destroy with --remove-data flag."""
        # Create dev environment with data
        dev_app_dir = project_with_deployed_app / "apps" / "dev" / "directus"
        dev_app_dir.mkdir(parents=True, exist_ok=True)
        (dev_app_dir / "docker-compose.yml").write_text("services:\n")

        data_dir = project_with_deployed_app / "data" / "dev"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "test.db").write_text("data")

        result = runner.invoke(
            app, ["env", "destroy", "dev", "--remove-data", "--force"]
        )

        assert result.exit_code == 0
        assert not data_dir.exists()

    def test_destroy_prod_requires_force(
        self, project_dir: Path, runner: CliRunner
    ):
        """Test destroying prod requires confirmation or --force."""
        result = runner.invoke(app, ["env", "destroy", "prod"], input="n\n")

        # Should abort when user declines
        assert result.exit_code == 1 or "Aborted" in result.stdout

    def test_destroy_not_found(self, project_dir: Path, runner: CliRunner):
        """Test destroy fails when environment not found."""
        result = runner.invoke(app, ["env", "destroy", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_destroy_prod_with_force(
        self, project_with_deployed_app: Path, runner: CliRunner, mock_docker_success
    ):
        """Test destroying prod with --force skips confirmation."""
        # Create prod environment
        prod_app_dir = project_with_deployed_app / "apps" / "prod" / "directus"
        prod_app_dir.mkdir(parents=True, exist_ok=True)
        (prod_app_dir / "docker-compose.yml").write_text("services:\n")

        result = runner.invoke(app, ["env", "destroy", "prod", "--force"])

        assert result.exit_code == 0
        assert "destroyed" in result.stdout
