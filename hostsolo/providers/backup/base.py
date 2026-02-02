"""Abstract base class for backup providers."""

from abc import ABC, abstractmethod
from pathlib import Path


class BackupProvider(ABC):
    """Abstract backup provider interface."""

    @abstractmethod
    def upload_file(self, local_path: Path, remote_key: str) -> None:
        """Upload a single file to the backup storage.

        Args:
            local_path: Path to the local file
            remote_key: The key/path in the remote storage
        """
        pass

    @abstractmethod
    def upload_directory(self, local_path: Path, remote_prefix: str) -> None:
        """Upload a directory recursively to the backup storage.

        Args:
            local_path: Path to the local directory
            remote_prefix: The prefix/path in the remote storage
        """
        pass

    @abstractmethod
    def download_file(self, remote_key: str, local_path: Path) -> None:
        """Download a single file from the backup storage.

        Args:
            remote_key: The key/path in the remote storage
            local_path: Path to save the file locally
        """
        pass

    @abstractmethod
    def download_directory(self, remote_prefix: str, local_path: Path) -> None:
        """Download a directory from the backup storage.

        Args:
            remote_prefix: The prefix/path in the remote storage
            local_path: Path to save the directory locally
        """
        pass

    @abstractmethod
    def list_backups(self, prefix: str) -> list[str]:
        """List all backups with a given prefix.

        Args:
            prefix: The prefix to filter backups

        Returns:
            List of backup keys/paths
        """
        pass

    @abstractmethod
    def delete_backup(self, prefix: str) -> None:
        """Delete all files with a given prefix.

        Args:
            prefix: The prefix of files to delete
        """
        pass
