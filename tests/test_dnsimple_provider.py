"""Tests for the DNSimple DNS provider."""

from unittest.mock import MagicMock, patch

import pytest

from hostsolo.providers.dns.dnsimple import DNSimpleProvider


class TestDNSimpleProviderInit:
    """Tests for DNSimpleProvider initialization."""

    def test_creates_client_with_headers(self):
        """Test provider creates httpx client with correct headers."""
        with patch("httpx.Client") as mock_client:
            provider = DNSimpleProvider(token="test-token", account_id="12345")

            mock_client.assert_called_once()
            call_kwargs = mock_client.call_args[1]
            assert call_kwargs["base_url"] == "https://api.dnsimple.com/v2"
            assert "Authorization" in call_kwargs["headers"]
            assert "Bearer test-token" in call_kwargs["headers"]["Authorization"]


class TestListRecords:
    """Tests for DNSimpleProvider.list_records()."""

    def test_list_records_success(self):
        """Test listing DNS records successfully."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": [
                    {"id": 1, "type": "A", "name": "", "content": "1.2.3.4", "ttl": 3600},
                    {"id": 2, "type": "A", "name": "dev", "content": "5.6.7.8", "ttl": 3600},
                ]
            }
            mock_client.get.return_value = mock_response

            provider = DNSimpleProvider(token="test", account_id="12345")
            records = provider.list_records("example.com")

            assert len(records) == 2
            assert records[0]["name"] == "@"  # Empty string converted to @
            assert records[1]["name"] == "dev"
            mock_client.get.assert_called_with("/12345/zones/example.com/records")

    def test_list_records_transforms_response(self):
        """Test list_records transforms API response correctly."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": [
                    {"id": 1, "type": "CNAME", "name": "www", "content": "example.com", "ttl": 1800},
                ]
            }
            mock_client.get.return_value = mock_response

            provider = DNSimpleProvider(token="test", account_id="12345")
            records = provider.list_records("example.com")

            record = records[0]
            assert record["id"] == 1
            assert record["type"] == "CNAME"
            assert record["name"] == "www"
            assert record["content"] == "example.com"
            assert record["ttl"] == 1800

    def test_list_records_empty(self):
        """Test listing records when none exist."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_response = MagicMock()
            mock_response.json.return_value = {"data": []}
            mock_client.get.return_value = mock_response

            provider = DNSimpleProvider(token="test", account_id="12345")
            records = provider.list_records("example.com")

            assert records == []

    def test_list_records_api_error(self):
        """Test list_records raises on API error."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = Exception("API Error")
            mock_client.get.return_value = mock_response

            provider = DNSimpleProvider(token="test", account_id="12345")

            with pytest.raises(Exception, match="API Error"):
                provider.list_records("example.com")


class TestFindRecord:
    """Tests for DNSimpleProvider._find_record()."""

    def test_find_record_exists(self):
        """Test finding an existing record."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": [
                    {"id": 1, "type": "A", "name": "dev", "content": "1.2.3.4", "ttl": 3600},
                    {"id": 2, "type": "CNAME", "name": "www", "content": "example.com", "ttl": 3600},
                ]
            }
            mock_client.get.return_value = mock_response

            provider = DNSimpleProvider(token="test", account_id="12345")
            record = provider._find_record("example.com", "dev", "A")

            assert record is not None
            assert record["id"] == 1
            assert record["name"] == "dev"

    def test_find_record_not_found(self):
        """Test finding a record that doesn't exist."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": [
                    {"id": 1, "type": "A", "name": "dev", "content": "1.2.3.4", "ttl": 3600},
                ]
            }
            mock_client.get.return_value = mock_response

            provider = DNSimpleProvider(token="test", account_id="12345")
            record = provider._find_record("example.com", "staging", "A")

            assert record is None

    def test_find_record_root_domain(self):
        """Test finding root domain record using @ notation."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": [
                    {"id": 1, "type": "A", "name": "", "content": "1.2.3.4", "ttl": 3600},
                ]
            }
            mock_client.get.return_value = mock_response

            provider = DNSimpleProvider(token="test", account_id="12345")
            record = provider._find_record("example.com", "@", "A")

            assert record is not None
            assert record["id"] == 1


class TestUpsertARecord:
    """Tests for DNSimpleProvider.upsert_a_record()."""

    def test_create_new_record(self):
        """Test creating a new A record."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Mock list_records to return empty (no existing record)
            list_response = MagicMock()
            list_response.json.return_value = {"data": []}
            mock_client.get.return_value = list_response

            # Mock create response
            create_response = MagicMock()
            mock_client.post.return_value = create_response

            provider = DNSimpleProvider(token="test", account_id="12345")
            provider.upsert_a_record("example.com", "dev", "1.2.3.4")

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "/12345/zones/example.com/records"
            assert call_args[1]["json"]["name"] == "dev"
            assert call_args[1]["json"]["type"] == "A"
            assert call_args[1]["json"]["content"] == "1.2.3.4"

    def test_update_existing_record(self):
        """Test updating an existing A record."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Mock list_records to return existing record
            list_response = MagicMock()
            list_response.json.return_value = {
                "data": [
                    {"id": 42, "type": "A", "name": "dev", "content": "old.ip", "ttl": 3600},
                ]
            }
            mock_client.get.return_value = list_response

            # Mock update response
            update_response = MagicMock()
            mock_client.patch.return_value = update_response

            provider = DNSimpleProvider(token="test", account_id="12345")
            provider.upsert_a_record("example.com", "dev", "1.2.3.4")

            mock_client.patch.assert_called_once()
            call_args = mock_client.patch.call_args
            assert "/12345/zones/example.com/records/42" in call_args[0][0]
            assert call_args[1]["json"]["content"] == "1.2.3.4"

    def test_upsert_root_domain(self):
        """Test creating A record for root domain."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            list_response = MagicMock()
            list_response.json.return_value = {"data": []}
            mock_client.get.return_value = list_response

            create_response = MagicMock()
            mock_client.post.return_value = create_response

            provider = DNSimpleProvider(token="test", account_id="12345")
            provider.upsert_a_record("example.com", "@", "1.2.3.4")

            call_args = mock_client.post.call_args
            assert call_args[1]["json"]["name"] == ""  # Root domain uses empty string

    def test_upsert_api_error(self):
        """Test upsert_a_record raises on API error."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            list_response = MagicMock()
            list_response.json.return_value = {"data": []}
            mock_client.get.return_value = list_response

            create_response = MagicMock()
            create_response.raise_for_status.side_effect = Exception("API Error")
            mock_client.post.return_value = create_response

            provider = DNSimpleProvider(token="test", account_id="12345")

            with pytest.raises(Exception, match="API Error"):
                provider.upsert_a_record("example.com", "dev", "1.2.3.4")


class TestDeleteARecord:
    """Tests for DNSimpleProvider.delete_a_record()."""

    def test_delete_existing_record(self):
        """Test deleting an existing A record."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Mock list_records to return existing record
            list_response = MagicMock()
            list_response.json.return_value = {
                "data": [
                    {"id": 42, "type": "A", "name": "dev", "content": "1.2.3.4", "ttl": 3600},
                ]
            }
            mock_client.get.return_value = list_response

            delete_response = MagicMock()
            mock_client.delete.return_value = delete_response

            provider = DNSimpleProvider(token="test", account_id="12345")
            provider.delete_a_record("example.com", "dev")

            mock_client.delete.assert_called_once()
            call_args = mock_client.delete.call_args
            assert "/12345/zones/example.com/records/42" in call_args[0][0]

    def test_delete_nonexistent_record(self):
        """Test deleting a record that doesn't exist (no-op)."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            list_response = MagicMock()
            list_response.json.return_value = {"data": []}
            mock_client.get.return_value = list_response

            provider = DNSimpleProvider(token="test", account_id="12345")
            provider.delete_a_record("example.com", "dev")

            # Should not call delete if record doesn't exist
            mock_client.delete.assert_not_called()

    def test_delete_api_error(self):
        """Test delete_a_record raises on API error."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            list_response = MagicMock()
            list_response.json.return_value = {
                "data": [
                    {"id": 42, "type": "A", "name": "dev", "content": "1.2.3.4", "ttl": 3600},
                ]
            }
            mock_client.get.return_value = list_response

            delete_response = MagicMock()
            delete_response.raise_for_status.side_effect = Exception("API Error")
            mock_client.delete.return_value = delete_response

            provider = DNSimpleProvider(token="test", account_id="12345")

            with pytest.raises(Exception, match="API Error"):
                provider.delete_a_record("example.com", "dev")


class TestUpsertCnameRecord:
    """Tests for DNSimpleProvider.upsert_cname_record()."""

    def test_create_cname_record(self):
        """Test creating a new CNAME record."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            list_response = MagicMock()
            list_response.json.return_value = {"data": []}
            mock_client.get.return_value = list_response

            create_response = MagicMock()
            mock_client.post.return_value = create_response

            provider = DNSimpleProvider(token="test", account_id="12345")
            provider.upsert_cname_record("example.com", "www", "example.com")

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[1]["json"]["type"] == "CNAME"
            assert call_args[1]["json"]["name"] == "www"
            assert call_args[1]["json"]["content"] == "example.com"

    def test_update_cname_record(self):
        """Test updating an existing CNAME record."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            list_response = MagicMock()
            list_response.json.return_value = {
                "data": [
                    {"id": 42, "type": "CNAME", "name": "www", "content": "old.example.com", "ttl": 3600},
                ]
            }
            mock_client.get.return_value = list_response

            update_response = MagicMock()
            mock_client.patch.return_value = update_response

            provider = DNSimpleProvider(token="test", account_id="12345")
            provider.upsert_cname_record("example.com", "www", "new.example.com")

            mock_client.patch.assert_called_once()
            call_args = mock_client.patch.call_args
            assert call_args[1]["json"]["content"] == "new.example.com"
