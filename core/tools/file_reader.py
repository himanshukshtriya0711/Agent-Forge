"""
File Reader Tool
Provides safe file reading operations within project workspace
"""

import os
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from django.conf import settings

logger = logging.getLogger("agentforge.tools")


class FileReader:
    """
    Safe file reader that operates within project workspace boundaries
    """

    # File extensions we support reading
    SUPPORTED_EXTENSIONS = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss",
        ".json", ".yaml", ".yml", ".md", ".txt", ".env", ".gitignore",
        ".toml", ".ini", ".cfg", ".sql", ".sh", ".bat", ".ps1",
    }

    # Maximum file size to read (5MB)
    MAX_FILE_SIZE = 5 * 1024 * 1024

    def __init__(self, project_path: Optional[Path] = None):
        """
        Initialize FileReader

        Args:
            project_path: Root path of the project to read from
        """
        self.project_path = Path(project_path) if project_path else settings.PROJECTS_DIR
        self.project_path = self.project_path.resolve()

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
        # Convert to Path and resolve
        path = Path(file_path)
        if not path.is_absolute():
            path = self.project_path / path
        path = path.resolve()

        # Security check: ensure path is within project
        try:
            path.relative_to(self.project_path)
        except ValueError:
            raise ValueError(f"Access denied: Path {file_path} is outside project workspace")

        return path

    def read_file(self, file_path: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """
        Read a file and return its contents

        Args:
            file_path: Path to the file
            encoding: File encoding

        Returns:
            Dictionary with file content and metadata
        """
        try:
            path = self._validate_path(file_path)

            if not path.exists():
                return {
                    "success": False,
                    "error": f"File not found: {file_path}",
                    "content": None,
                }

            if not path.is_file():
                return {
                    "success": False,
                    "error": f"Not a file: {file_path}",
                    "content": None,
                }

            # Check file size
            file_size = path.stat().st_size
            if file_size > self.MAX_FILE_SIZE:
                return {
                    "success": False,
                    "error": f"File too large: {file_size} bytes (max: {self.MAX_FILE_SIZE})",
                    "content": None,
                }

            # Read file content
            with open(path, "r", encoding=encoding) as f:
                content = f.read()

            return {
                "success": True,
                "content": content,
                "path": str(path.relative_to(self.project_path)),
                "size": file_size,
                "lines": content.count("\n") + 1,
                "extension": path.suffix,
            }

        except UnicodeDecodeError:
            return {
                "success": False,
                "error": f"Cannot decode file (not text): {file_path}",
                "content": None,
            }
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return {
                "success": False,
                "error": str(e),
                "content": None,
            }

    def read_lines(
        self, file_path: str, start_line: int, end_line: int, encoding: str = "utf-8"
    ) -> Dict[str, Any]:
        """
        Read specific lines from a file

        Args:
            file_path: Path to the file
            start_line: Starting line number (1-indexed)
            end_line: Ending line number (inclusive)
            encoding: File encoding

        Returns:
            Dictionary with line content and metadata
        """
        result = self.read_file(file_path, encoding)
        if not result["success"]:
            return result

        lines = result["content"].split("\n")
        total_lines = len(lines)

        # Validate line numbers
        start_line = max(1, start_line)
        end_line = min(total_lines, end_line)

        if start_line > total_lines:
            return {
                "success": False,
                "error": f"Start line {start_line} exceeds file length ({total_lines} lines)",
                "content": None,
            }

        # Extract lines (convert to 0-indexed)
        selected_lines = lines[start_line - 1 : end_line]

        return {
            "success": True,
            "content": "\n".join(selected_lines),
            "path": result["path"],
            "start_line": start_line,
            "end_line": end_line,
            "total_lines": total_lines,
        }

    def list_directory(
        self, dir_path: str = ".", recursive: bool = False, include_hidden: bool = False
    ) -> Dict[str, Any]:
        """
        List contents of a directory

        Args:
            dir_path: Path to directory
            recursive: Whether to list recursively
            include_hidden: Include hidden files/folders

        Returns:
            Dictionary with directory contents
        """
        try:
            path = self._validate_path(dir_path)

            if not path.exists():
                return {
                    "success": False,
                    "error": f"Directory not found: {dir_path}",
                    "contents": [],
                }

            if not path.is_dir():
                return {
                    "success": False,
                    "error": f"Not a directory: {dir_path}",
                    "contents": [],
                }

            contents = []
            pattern = "**/*" if recursive else "*"

            for item in path.glob(pattern):
                # Skip hidden files if not requested
                if not include_hidden and item.name.startswith("."):
                    continue

                relative_path = item.relative_to(self.project_path)
                contents.append({
                    "name": item.name,
                    "path": str(relative_path),
                    "is_file": item.is_file(),
                    "is_dir": item.is_dir(),
                    "extension": item.suffix if item.is_file() else None,
                    "size": item.stat().st_size if item.is_file() else None,
                })

            return {
                "success": True,
                "path": str(path.relative_to(self.project_path)),
                "contents": sorted(contents, key=lambda x: (not x["is_dir"], x["name"])),
                "count": len(contents),
            }

        except Exception as e:
            logger.error(f"Error listing directory {dir_path}: {e}")
            return {
                "success": False,
                "error": str(e),
                "contents": [],
            }

    def get_project_structure(self, max_depth: int = 4) -> str:
        """
        Get a tree-like representation of the project structure

        Args:
            max_depth: Maximum depth to traverse

        Returns:
            String representation of project structure
        """
        def build_tree(path: Path, prefix: str = "", depth: int = 0) -> List[str]:
            if depth >= max_depth:
                return []

            lines = []
            try:
                items = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name))
            except PermissionError:
                return []

            # Filter out hidden and common ignored directories
            ignored = {".git", ".venv", "venv", "__pycache__", "node_modules", ".idea", ".vscode"}
            items = [i for i in items if i.name not in ignored and not i.name.startswith(".")]

            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                connector = "└── " if is_last else "├── "
                lines.append(f"{prefix}{connector}{item.name}")

                if item.is_dir():
                    extension = "    " if is_last else "│   "
                    lines.extend(build_tree(item, prefix + extension, depth + 1))

            return lines

        tree_lines = [self.project_path.name + "/"]
        tree_lines.extend(build_tree(self.project_path))
        return "\n".join(tree_lines)

    def search_files(
        self, pattern: str, file_extensions: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for files matching a pattern

        Args:
            pattern: Glob pattern to match
            file_extensions: Optional list of extensions to filter

        Returns:
            List of matching files
        """
        results = []

        try:
            for file_path in self.project_path.rglob(pattern):
                # Skip hidden and ignored directories
                if any(part.startswith(".") for part in file_path.parts):
                    continue
                if any(part in {"__pycache__", "node_modules", ".venv"} for part in file_path.parts):
                    continue

                if file_path.is_file():
                    if file_extensions and file_path.suffix not in file_extensions:
                        continue

                    results.append({
                        "name": file_path.name,
                        "path": str(file_path.relative_to(self.project_path)),
                        "extension": file_path.suffix,
                        "size": file_path.stat().st_size,
                    })

        except Exception as e:
            logger.error(f"Error searching files: {e}")

        return results
