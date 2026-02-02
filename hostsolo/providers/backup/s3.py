"""S3-compatible backup provider implementation."""

from pathlib import Path

import boto3
from botocore.config import Config

from hostsolo.providers.backup.base import BackupProvider


class S3BackupProvider(BackupProvider):
    """Backup provider for S3-compatible storage.

    Works with:
    - AWS S3
    - Backblaze B2 (S3-compatible API)
    - MinIO
    - DigitalOcean Spaces
    - Any S3-compatible storage
    """

    def __init__(
        self,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        endpoint_url: str | None = None,
    ):
        """Initialize S3 backup provider.

        Args:
            bucket: S3 bucket name
            access_key: AWS access key ID
            secret_key: AWS secret access key
            region: AWS region (default: us-east-1)
            endpoint_url: Custom endpoint URL for S3-compatible providers
        """
        self.bucket = bucket

        # Configure the S3 client
        config = Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
        )

        self.client = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            endpoint_url=endpoint_url,
            config=config,
        )

    def upload_file(self, local_path: Path, remote_key: str) -> None:
        """Upload a single file to S3."""
        self.client.upload_file(str(local_path), self.bucket, remote_key)

    def upload_directory(self, local_path: Path, remote_prefix: str) -> None:
        """Upload a directory recursively to S3."""
        if not local_path.is_dir():
            # Single file, upload directly
            self.upload_file(local_path, remote_prefix)
            return

        for file_path in local_path.rglob("*"):
            if file_path.is_file():
                # Calculate relative path
                relative_path = file_path.relative_to(local_path)
                remote_key = f"{remote_prefix}/{relative_path}"
                self.upload_file(file_path, remote_key)

    def download_file(self, remote_key: str, local_path: Path) -> None:
        """Download a single file from S3."""
        # Ensure parent directory exists
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, remote_key, str(local_path))

    def download_directory(self, remote_prefix: str, local_path: Path) -> None:
        """Download a directory from S3."""
        # List all objects with the prefix
        paginator = self.client.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=self.bucket, Prefix=remote_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                # Calculate relative path from prefix
                relative_path = key[len(remote_prefix):].lstrip("/")
                if relative_path:
                    file_path = local_path / relative_path
                    self.download_file(key, file_path)

    def list_backups(self, prefix: str) -> list[str]:
        """List all backups with a given prefix."""
        backups = []
        paginator = self.client.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                backups.append(obj["Key"])

        return backups

    def delete_backup(self, prefix: str) -> None:
        """Delete all files with a given prefix."""
        # List all objects to delete
        objects_to_delete = []
        paginator = self.client.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                objects_to_delete.append({"Key": obj["Key"]})

        # Delete in batches of 1000 (S3 limit)
        while objects_to_delete:
            batch = objects_to_delete[:1000]
            objects_to_delete = objects_to_delete[1000:]

            self.client.delete_objects(
                Bucket=self.bucket,
                Delete={"Objects": batch},
            )
