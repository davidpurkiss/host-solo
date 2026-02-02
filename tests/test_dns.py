"""Tests for the dns command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import click.exceptions
import pytest
import yaml
from typer.testing import CliRunner

from hostsolo.cli import app
from hostsolo.commands.dns import get_dns_provider, get_public_ip


class TestGetDnsProvider:
    """Tests for get_dns_provider() function."""

    def test_dnsimple_provider(self, project_dir: Path, mock_env_settings):
        """Test getting DNSimple provider with valid credentials."""
        with patch("hostsolo.providers.dns.dnsimple.httpx.Client"):
            provider = get_dns_provider()
            assert provider is not None
            assert provider.account_id == "12345"

    def test_missing_token(self, project_dir: Path, mock_env_settings_missing_dns):
        """Test get_dns_provider exits when token is missing."""
        with pytest.raises(click.exceptions.Exit) as exc_info:
            get_dns_provider()
        assert exc_info.value.exit_code == 1

    def test_missing_account_id(self, project_dir: Path):
        """Test get_dns_provider exits when account_id is missing."""
        from hostsolo.config import EnvironmentSettings

        settings = EnvironmentSettings(
            dnsimple_token="token",
            dnsimple_account_id=None,
        )
        with patch("hostsolo.commands.dns.load_env_settings", return_value=settings):
            with pytest.raises(click.exceptions.Exit) as exc_info:
                get_dns_provider()
            assert exc_info.value.exit_code == 1

    def test_unknown_provider(self, project_dir: Path, mock_env_settings):
        """Test get_dns_provider exits for unknown provider."""
        config_path = project_dir / "hostsolo.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)
        config["dns"]["provider"] = "unknown"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        with pytest.raises(click.exceptions.Exit) as exc_info:
            get_dns_provider()
        assert exc_info.value.exit_code == 1


class TestGetPublicIp:
    """Tests for get_public_ip() function."""

    def test_first_service_success(self):
        """Test get_public_ip returns IP from first successful service."""
        import httpx

        with patch.object(httpx, "get") as mock_get:
            mock_response = MagicMock(status_code=200, text="192.168.1.100")
            mock_get.return_value = mock_response

            ip = get_public_ip()

            assert ip == "192.168.1.100"
            assert mock_get.call_count == 1

    def test_fallback_service(self):
        """Test get_public_ip falls back when first service fails."""
        import httpx

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.RequestError("Connection failed")
            return MagicMock(status_code=200, text="10.0.0.1")

        with patch.object(httpx, "get", side_effect=side_effect):
            ip = get_public_ip()

            assert ip == "10.0.0.1"
            assert call_count == 2

    def test_all_services_fail(self):
        """Test get_public_ip exits when all services fail."""
        import httpx

        with patch.object(httpx, "get", side_effect=httpx.RequestError("Failed")):
            with pytest.raises(click.exceptions.Exit) as exc_info:
                get_public_ip()
            assert exc_info.value.exit_code == 1


class TestDnsSetup:
    """Tests for dns setup command."""

    def test_setup_success(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test successful DNS setup."""
        with patch("hostsolo.commands.dns.get_dns_provider") as mock_provider:
            mock_dns = MagicMock()
            mock_provider.return_value = mock_dns
            with patch("hostsolo.commands.dns.get_public_ip", return_value="1.2.3.4"):
                result = runner.invoke(app, ["dns", "setup", "--env", "prod"])

                assert result.exit_code == 0
                assert "A record created/updated" in result.stdout
                mock_dns.upsert_a_record.assert_called_once()

    def test_setup_custom_ip(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test DNS setup with custom IP."""
        with patch("hostsolo.commands.dns.get_dns_provider") as mock_provider:
            mock_dns = MagicMock()
            mock_provider.return_value = mock_dns

            result = runner.invoke(
                app, ["dns", "setup", "--env", "prod", "--ip", "5.6.7.8"]
            )

            assert result.exit_code == 0
            mock_dns.upsert_a_record.assert_called_with(
                domain="example.com",
                name="@",
                ip="5.6.7.8",
            )

    def test_setup_root_domain(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test DNS setup for root domain (prod environment)."""
        with patch("hostsolo.commands.dns.get_dns_provider") as mock_provider:
            mock_dns = MagicMock()
            mock_provider.return_value = mock_dns
            with patch("hostsolo.commands.dns.get_public_ip", return_value="1.2.3.4"):
                result = runner.invoke(app, ["dns", "setup", "--env", "prod"])

                assert result.exit_code == 0
                # Prod has empty subdomain, should use "@"
                mock_dns.upsert_a_record.assert_called_with(
                    domain="example.com",
                    name="@",
                    ip="1.2.3.4",
                )

    def test_setup_subdomain(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test DNS setup for subdomain environment."""
        with patch("hostsolo.commands.dns.get_dns_provider") as mock_provider:
            mock_dns = MagicMock()
            mock_provider.return_value = mock_dns
            with patch("hostsolo.commands.dns.get_public_ip", return_value="1.2.3.4"):
                result = runner.invoke(app, ["dns", "setup", "--env", "dev"])

                assert result.exit_code == 0
                mock_dns.upsert_a_record.assert_called_with(
                    domain="example.com",
                    name="dev",
                    ip="1.2.3.4",
                )

    def test_setup_api_failure(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test DNS setup handles API failure."""
        with patch("hostsolo.commands.dns.get_dns_provider") as mock_provider:
            mock_dns = MagicMock()
            mock_dns.upsert_a_record.side_effect = Exception("API Error")
            mock_provider.return_value = mock_dns
            with patch("hostsolo.commands.dns.get_public_ip", return_value="1.2.3.4"):
                result = runner.invoke(app, ["dns", "setup", "--env", "prod"])

                assert result.exit_code == 1
                assert "Failed to set up DNS" in result.stdout


class TestDnsListRecords:
    """Tests for dns list command."""

    def test_list_success(
        self, project_dir: Path, runner: CliRunner, mock_env_settings, sample_dns_records
    ):
        """Test listing DNS records."""
        with patch("hostsolo.commands.dns.get_dns_provider") as mock_provider:
            mock_dns = MagicMock()
            mock_dns.list_records.return_value = sample_dns_records
            mock_provider.return_value = mock_dns

            result = runner.invoke(app, ["dns", "list"])

            assert result.exit_code == 0
            assert "A" in result.stdout
            assert "192.168.1.100" in result.stdout

    def test_list_empty(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test listing DNS records when none exist."""
        with patch("hostsolo.commands.dns.get_dns_provider") as mock_provider:
            mock_dns = MagicMock()
            mock_dns.list_records.return_value = []
            mock_provider.return_value = mock_dns

            result = runner.invoke(app, ["dns", "list"])

            assert result.exit_code == 0

    def test_list_api_failure(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test list handles API failure."""
        with patch("hostsolo.commands.dns.get_dns_provider") as mock_provider:
            mock_dns = MagicMock()
            mock_dns.list_records.side_effect = Exception("API Error")
            mock_provider.return_value = mock_dns

            result = runner.invoke(app, ["dns", "list"])

            assert result.exit_code == 1
            assert "Failed to list records" in result.stdout


class TestDnsDelete:
    """Tests for dns delete command."""

    def test_delete_with_force(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test deleting DNS record with --force."""
        with patch("hostsolo.commands.dns.get_dns_provider") as mock_provider:
            mock_dns = MagicMock()
            mock_provider.return_value = mock_dns

            result = runner.invoke(
                app, ["dns", "delete", "--env", "dev", "--force"]
            )

            assert result.exit_code == 0
            assert "A record deleted" in result.stdout
            mock_dns.delete_a_record.assert_called_once()

    def test_delete_with_confirmation(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test deleting DNS record with confirmation."""
        with patch("hostsolo.commands.dns.get_dns_provider") as mock_provider:
            mock_dns = MagicMock()
            mock_provider.return_value = mock_dns

            result = runner.invoke(
                app, ["dns", "delete", "--env", "dev"], input="y\n"
            )

            assert result.exit_code == 0
            mock_dns.delete_a_record.assert_called_once()

    def test_delete_cancelled(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test cancelling DNS record deletion."""
        with patch("hostsolo.commands.dns.get_dns_provider") as mock_provider:
            mock_dns = MagicMock()
            mock_provider.return_value = mock_dns

            result = runner.invoke(
                app, ["dns", "delete", "--env", "dev"], input="n\n"
            )

            # Should abort
            assert "Aborted" in result.stdout or result.exit_code == 1
            mock_dns.delete_a_record.assert_not_called()

    def test_delete_api_failure(
        self, project_dir: Path, runner: CliRunner, mock_env_settings
    ):
        """Test delete handles API failure."""
        with patch("hostsolo.commands.dns.get_dns_provider") as mock_provider:
            mock_dns = MagicMock()
            mock_dns.delete_a_record.side_effect = Exception("API Error")
            mock_provider.return_value = mock_dns

            result = runner.invoke(
                app, ["dns", "delete", "--env", "dev", "--force"]
            )

            assert result.exit_code == 1
            assert "Failed to delete DNS record" in result.stdout
