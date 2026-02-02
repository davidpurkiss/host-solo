"""Tests for the S3 backup provider."""

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from hostsolo.providers.backup.s3 import S3BackupProvider


class TestS3ProviderInit:
    """Tests for S3BackupProvider initialization."""

    def test_creates_client(self):
        """Test provider creates boto3 client."""
        with patch("boto3.client") as mock_boto:
            provider = S3BackupProvider(
                bucket="test-bucket",
                access_key="AKIATEST",
                secret_key="secret123",
            )

            mock_boto.assert_called_once_with(
                "s3",
                aws_access_key_id="AKIATEST",
                aws_secret_access_key="secret123",
                region_name="us-east-1",
                endpoint_url=None,
                config=mock_boto.call_args[1]["config"],
            )
            assert provider.bucket == "test-bucket"

    def test_creates_client_with_endpoint_url(self):
        """Test provider creates client with custom endpoint URL."""
        with patch("boto3.client") as mock_boto:
            provider = S3BackupProvider(
                bucket="test-bucket",
                access_key="AKIATEST",
                secret_key="secret123",
                endpoint_url="https://s3.custom.com",
            )

            call_kwargs = mock_boto.call_args[1]
            assert call_kwargs["endpoint_url"] == "https://s3.custom.com"


class TestUploadFile:
    """Tests for S3BackupProvider.upload_file()."""

    def test_upload_file_success(self, tmp_path: Path):
        """Test uploading a single file."""
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client

            provider = S3BackupProvider(
                bucket="test-bucket",
                access_key="key",
                secret_key="secret",
            )

            test_file = tmp_path / "test.txt"
            test_file.write_text("test content")

            provider.upload_file(test_file, "backups/test.txt")

            mock_client.upload_file.assert_called_once_with(
                str(test_file), "test-bucket", "backups/test.txt"
            )

    def test_upload_file_correct_method(self, tmp_path: Path):
        """Test upload_file calls correct boto3 method."""
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client

            provider = S3BackupProvider(
                bucket="my-bucket",
                access_key="key",
                secret_key="secret",
            )

            test_file = tmp_path / "data.db"
            test_file.write_text("data")

            provider.upload_file(test_file, "prod/app/data.db")

            # Verify the correct method with correct arguments
            assert mock_client.upload_file.called
            args = mock_client.upload_file.call_args[0]
            assert args[1] == "my-bucket"
            assert args[2] == "prod/app/data.db"


class TestUploadDirectory:
    """Tests for S3BackupProvider.upload_directory()."""

    def test_upload_single_file(self, tmp_path: Path):
        """Test uploading a single file as directory."""
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client

            provider = S3BackupProvider(
                bucket="test-bucket",
                access_key="key",
                secret_key="secret",
            )

            test_file = tmp_path / "test.txt"
            test_file.write_text("content")

            provider.upload_directory(test_file, "backups/test.txt")

            # Single file should be uploaded directly
            mock_client.upload_file.assert_called_once()

    def test_upload_directory_recursive(self, tmp_path: Path):
        """Test uploading directory recursively."""
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client

            provider = S3BackupProvider(
                bucket="test-bucket",
                access_key="key",
                secret_key="secret",
            )

            # Create directory structure
            data_dir = tmp_path / "data"
            data_dir.mkdir()
            (data_dir / "file1.txt").write_text("file1")
            (data_dir / "file2.txt").write_text("file2")
            subdir = data_dir / "subdir"
            subdir.mkdir()
            (subdir / "file3.txt").write_text("file3")

            provider.upload_directory(data_dir, "backups/data")

            # Should upload all 3 files
            assert mock_client.upload_file.call_count == 3

    def test_upload_directory_preserves_structure(self, tmp_path: Path):
        """Test upload preserves directory structure."""
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client

            provider = S3BackupProvider(
                bucket="test-bucket",
                access_key="key",
                secret_key="secret",
            )

            data_dir = tmp_path / "data"
            data_dir.mkdir()
            subdir = data_dir / "uploads"
            subdir.mkdir()
            (subdir / "image.jpg").write_text("image")

            provider.upload_directory(data_dir, "backups/data")

            # Check that path structure is preserved
            call_args = mock_client.upload_file.call_args[0]
            assert "backups/data/uploads/image.jpg" in call_args[2]


class TestDownloadFile:
    """Tests for S3BackupProvider.download_file()."""

    def test_download_file_success(self, tmp_path: Path):
        """Test downloading a single file."""
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client

            provider = S3BackupProvider(
                bucket="test-bucket",
                access_key="key",
                secret_key="secret",
            )

            local_path = tmp_path / "downloaded.txt"

            provider.download_file("backups/test.txt", local_path)

            mock_client.download_file.assert_called_once_with(
                "test-bucket", "backups/test.txt", str(local_path)
            )

    def test_download_file_creates_parent_dirs(self, tmp_path: Path):
        """Test download_file creates parent directories."""
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client

            provider = S3BackupProvider(
                bucket="test-bucket",
                access_key="key",
                secret_key="secret",
            )

            local_path = tmp_path / "deep" / "nested" / "path" / "file.txt"

            provider.download_file("backups/file.txt", local_path)

            # Parent directories should be created
            assert local_path.parent.exists()


class TestDownloadDirectory:
    """Tests for S3BackupProvider.download_directory()."""

    def test_download_directory_success(self, tmp_path: Path):
        """Test downloading a directory."""
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client

            # Mock paginator
            paginator = MagicMock()
            paginator.paginate.return_value = [
                {
                    "Contents": [
                        {"Key": "backups/data/file1.txt"},
                        {"Key": "backups/data/file2.txt"},
                    ]
                }
            ]
            mock_client.get_paginator.return_value = paginator

            provider = S3BackupProvider(
                bucket="test-bucket",
                access_key="key",
                secret_key="secret",
            )

            local_dir = tmp_path / "restored"

            provider.download_directory("backups/data", local_dir)

            # Should download both files
            assert mock_client.download_file.call_count == 2

    def test_download_directory_handles_pagination(self, tmp_path: Path):
        """Test download handles pagination correctly."""
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client

            # Mock paginator with multiple pages
            paginator = MagicMock()
            paginator.paginate.return_value = [
                {"Contents": [{"Key": "backups/data/file1.txt"}]},
                {"Contents": [{"Key": "backups/data/file2.txt"}]},
            ]
            mock_client.get_paginator.return_value = paginator

            provider = S3BackupProvider(
                bucket="test-bucket",
                access_key="key",
                secret_key="secret",
            )

            local_dir = tmp_path / "restored"

            provider.download_directory("backups/data", local_dir)

            # Should download from both pages
            assert mock_client.download_file.call_count == 2


class TestListBackups:
    """Tests for S3BackupProvider.list_backups()."""

    def test_list_backups_success(self):
        """Test listing backups."""
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client

            paginator = MagicMock()
            paginator.paginate.return_value = [
                {
                    "Contents": [
                        {"Key": "prod/app/2024-01-01/data.db"},
                        {"Key": "prod/app/2024-01-02/data.db"},
                    ]
                }
            ]
            mock_client.get_paginator.return_value = paginator

            provider = S3BackupProvider(
                bucket="test-bucket",
                access_key="key",
                secret_key="secret",
            )

            backups = provider.list_backups("prod/app/")

            assert len(backups) == 2
            assert "prod/app/2024-01-01/data.db" in backups

    def test_list_backups_empty(self):
        """Test listing backups when none exist."""
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client

            paginator = MagicMock()
            paginator.paginate.return_value = [{"Contents": []}]
            mock_client.get_paginator.return_value = paginator

            provider = S3BackupProvider(
                bucket="test-bucket",
                access_key="key",
                secret_key="secret",
            )

            backups = provider.list_backups("prod/app/")

            assert backups == []

    def test_list_backups_with_prefix(self):
        """Test listing backups with specific prefix."""
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client

            paginator = MagicMock()
            paginator.paginate.return_value = [{"Contents": []}]
            mock_client.get_paginator.return_value = paginator

            provider = S3BackupProvider(
                bucket="test-bucket",
                access_key="key",
                secret_key="secret",
            )

            provider.list_backups("prod/specific-app/")

            # Verify paginate was called with correct prefix
            call_kwargs = paginator.paginate.call_args[1]
            assert call_kwargs["Prefix"] == "prod/specific-app/"

    def test_list_backups_pagination(self):
        """Test list_backups handles pagination."""
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client

            paginator = MagicMock()
            paginator.paginate.return_value = [
                {"Contents": [{"Key": "backup1"}]},
                {"Contents": [{"Key": "backup2"}]},
                {"Contents": [{"Key": "backup3"}]},
            ]
            mock_client.get_paginator.return_value = paginator

            provider = S3BackupProvider(
                bucket="test-bucket",
                access_key="key",
                secret_key="secret",
            )

            backups = provider.list_backups("prefix/")

            assert len(backups) == 3


class TestDeleteBackup:
    """Tests for S3BackupProvider.delete_backup()."""

    def test_delete_backup_success(self):
        """Test deleting a backup."""
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client

            paginator = MagicMock()
            paginator.paginate.return_value = [
                {
                    "Contents": [
                        {"Key": "prod/app/2024-01-01/file1.txt"},
                        {"Key": "prod/app/2024-01-01/file2.txt"},
                    ]
                }
            ]
            mock_client.get_paginator.return_value = paginator

            provider = S3BackupProvider(
                bucket="test-bucket",
                access_key="key",
                secret_key="secret",
            )

            provider.delete_backup("prod/app/2024-01-01/")

            mock_client.delete_objects.assert_called_once()
            call_kwargs = mock_client.delete_objects.call_args[1]
            assert call_kwargs["Bucket"] == "test-bucket"
            assert len(call_kwargs["Delete"]["Objects"]) == 2

    def test_delete_backup_batches_large_delete(self):
        """Test delete batches when more than 1000 objects."""
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client

            # Create 1500 objects
            objects = [{"Key": f"prod/app/backup/file{i}.txt"} for i in range(1500)]
            paginator = MagicMock()
            paginator.paginate.return_value = [{"Contents": objects}]
            mock_client.get_paginator.return_value = paginator

            provider = S3BackupProvider(
                bucket="test-bucket",
                access_key="key",
                secret_key="secret",
            )

            provider.delete_backup("prod/app/backup/")

            # Should be called twice (1000 + 500)
            assert mock_client.delete_objects.call_count == 2

    def test_delete_backup_empty_prefix(self):
        """Test delete with no objects to delete."""
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client

            paginator = MagicMock()
            paginator.paginate.return_value = [{"Contents": []}]
            mock_client.get_paginator.return_value = paginator

            provider = S3BackupProvider(
                bucket="test-bucket",
                access_key="key",
                secret_key="secret",
            )

            provider.delete_backup("nonexistent/")

            # Should not call delete_objects if nothing to delete
            mock_client.delete_objects.assert_not_called()
