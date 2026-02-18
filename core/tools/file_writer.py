"""
File Writer Tool
Provides safe file writing operations within project workspace
"""

import os
import shutil
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from django.conf import settings

logger = logging.getLogger("agentforge.tools")


class FileWriter:
    """
    Safe file writer that operates within project workspace boundaries
    Creates backups before modifications
    """

    # Maximum file size to write (10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024

    def __init__(self, project_path: Optional[Path] = None):
        """
        Initialize FileWriter

        Args:
            project_path: Root path of the project to write to
        """
        self.project_path = Path(project_path) if project_path else settings.PROJECTS_DIR
        self.project_path = self.project_path.resolve()
        self.backup_dir = self.project_path / ".agentforge_backups"

    def _validate_path(self, file_path: str) -> Path:
        """
        Validate and resolve file path, ensuring it's within project boundaries

        Args:
            file_path: Relative or absolute path to file

        Returns:
            Resolved Path object

        Raises:
            ValueError: If path is outside project or invalid
        """
        path = Path(file_path)
        if not path.is_absolute():
            path = self.project_path / path
        path = path.resolve()

        # Security check: ensure path is within project
        try:
            path.relative_to(self.project_path)
        except ValueError:
            raise ValueError(f"Access denied: Path {file_path} is outside project workspace")

        # Prevent writing to backup directory
        if str(path).startswith(str(self.backup_dir)):
            raise ValueError("Cannot write to backup directory")

        return path

    def _create_backup(self, file_path: Path) -> Optional[Path]:
        """
        Create a backup of an existing file

        Args:
            file_path: Path to the file to backup

        Returns:
            Path to backup file or None if original doesn't exist
        """
        if not file_path.exists():
            return None

        # Create backup directory
        self.backup_dir.mkdir(exist_ok=True)

        # Create timestamped backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        relative_path = file_path.relative_to(self.project_path)
        backup_name = f"{relative_path.stem}_{timestamp}{relative_path.suffix}"
        backup_path = self.backup_dir / backup_name

        try:
            shutil.copy2(file_path, backup_path)
            logger.info(f"Created backup: {backup_path}")
            return backup_path
        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")
            return None

    def write_file(
        self,
        file_path: str,
        content: str,
        create_backup: bool = True,
        encoding: str = "utf-8",
    ) -> Dict[str, Any]:
        """
        Write content to a file

        Args:
            file_path: Path to the file
            content: Content to write
            create_backup: Whether to backup existing file
            encoding: File encoding

        Returns:
            Dictionary with operation result
        """
        try:
            path = self._validate_path(file_path)

            # Check content size
            content_size = len(content.encode(encoding))
            if content_size > self.MAX_FILE_SIZE:
                return {
                    "success": False,
                    "error": f"Content too large: {content_size} bytes (max: {self.MAX_FILE_SIZE})",
                }

            # Create parent directories if needed
            path.parent.mkdir(parents=True, exist_ok=True)

            # Backup existing file
            backup_path = None
            if create_backup and path.exists():
                backup_path = self._create_backup(path)

            # Write content
            with open(path, "w", encoding=encoding) as f:
                f.write(content)

            logger.info(f"Written file: {path}")

            return {
                "success": True,
                "path": str(path.relative_to(self.project_path)),
                "size": content_size,
                "backup_path": str(backup_path.relative_to(self.project_path)) if backup_path else None,
                "created": not path.exists(),
            }

        except Exception as e:
            logger.error(f"Error writing file {file_path}: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def create_file(
        self, file_path: str, content: str = "", encoding: str = "utf-8"
    ) -> Dict[str, Any]:
        """
        Create a new file (fails if file exists)

        Args:
            file_path: Path to the file
            content: Content to write
            encoding: File encoding

        Returns:
            Dictionary with operation result
        """
        try:
            path = self._validate_path(file_path)

            if path.exists():
                return {
                    "success": False,
                    "error": f"File already exists: {file_path}",
                }

            return self.write_file(file_path, content, create_backup=False, encoding=encoding)

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def create_directory(self, dir_path: str) -> Dict[str, Any]:
        """
        Create a new directory

        Args:
            dir_path: Path to the directory

        Returns:
            Dictionary with operation result
        """
        try:
            path = self._validate_path(dir_path)

            if path.exists():
                if path.is_dir():
                    return {
                        "success": True,
                        "path": str(path.relative_to(self.project_path)),
                        "message": "Directory already exists",
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Path exists but is not a directory: {dir_path}",
                    }

            path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created directory: {path}")

            return {
                "success": True,
                "path": str(path.relative_to(self.project_path)),
                "created": True,
            }

        except Exception as e:
            logger.error(f"Error creating directory {dir_path}: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def delete_file(self, file_path: str, create_backup: bool = True) -> Dict[str, Any]:
        """
        Delete a file (with optional backup)

        Args:
            file_path: Path to the file
            create_backup: Whether to backup before deletion

        Returns:
            Dictionary with operation result
        """
        try:
            path = self._validate_path(file_path)

            if not path.exists():
                return {
                    "success": False,
                    "error": f"File not found: {file_path}",
                }

            if not path.is_file():
                return {
                    "success": False,
                    "error": f"Not a file: {file_path}",
                }

            # Create backup before deletion
            backup_path = None
            if create_backup:
                backup_path = self._create_backup(path)

            path.unlink()
            logger.info(f"Deleted file: {path}")

            return {
                "success": True,
                "path": str(path.relative_to(self.project_path)),
                "backup_path": str(backup_path.relative_to(self.project_path)) if backup_path else None,
            }

        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def restore_backup(self, backup_name: str, target_path: str) -> Dict[str, Any]:
        """
        Restore a file from backup

        Args:
            backup_name: Name of the backup file
            target_path: Path to restore to

        Returns:
            Dictionary with operation result
        """
        try:
            backup_path = self.backup_dir / backup_name
            if not backup_path.exists():
                return {
                    "success": False,
                    "error": f"Backup not found: {backup_name}",
                }

            target = self._validate_path(target_path)
            shutil.copy2(backup_path, target)

            return {
                "success": True,
                "restored_from": backup_name,
                "restored_to": str(target.relative_to(self.project_path)),
            }

        except Exception as e:
            logger.error(f"Error restoring backup: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def list_backups(self) -> Dict[str, Any]:
        """
        List all available backups

        Returns:
            Dictionary with backup list
        """
        if not self.backup_dir.exists():
            return {
                "success": True,
                "backups": [],
                "count": 0,
            }

        backups = []
        for backup_file in self.backup_dir.iterdir():
            if backup_file.is_file():
                backups.append({
                    "name": backup_file.name,
                    "size": backup_file.stat().st_size,
                    "created": datetime.fromtimestamp(backup_file.stat().st_mtime).isoformat(),
                })

        return {
            "success": True,
            "backups": sorted(backups, key=lambda x: x["created"], reverse=True),
            "count": len(backups),
        }
