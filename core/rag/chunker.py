"""
Code Chunker
Provides intelligent code chunking with function-level granularity
"""

import ast
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from django.conf import settings

logger = logging.getLogger("agentforge.rag")


@dataclass
class CodeChunk:
    """Represents a chunk of code with metadata"""
    content: str
    file_path: str
    start_line: int
    end_line: int
    chunk_type: str  # function, class, method, module, block
    name: Optional[str] = None
    parent: Optional[str] = None
    docstring: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "chunk_type": self.chunk_type,
            "name": self.name,
            "parent": self.parent,
            "docstring": self.docstring,
        }


class CodeChunker:
    """
    Intelligent code chunker that extracts functions, classes, and logical blocks
    """

    # Supported file extensions
    SUPPORTED_EXTENSIONS = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".html": "html",
        ".css": "css",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".md": "markdown",
    }

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        min_chunk_size: int = 50,
    ):
        """
        Initialize CodeChunker

        Args:
            chunk_size: Target chunk size in characters
            chunk_overlap: Overlap between chunks
            min_chunk_size: Minimum chunk size
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def chunk_file(self, file_path: str, content: str) -> List[CodeChunk]:
        """
        Chunk a file based on its type

        Args:
            file_path: Path to the file
            content: File content

        Returns:
            List of CodeChunk objects
        """
        extension = Path(file_path).suffix.lower()
        language = self.SUPPORTED_EXTENSIONS.get(extension)

        if language == "python":
            return self._chunk_python(file_path, content)
        elif language in ("javascript", "typescript"):
            return self._chunk_javascript(file_path, content)
        else:
            return self._chunk_generic(file_path, content)

    def _chunk_python(self, file_path: str, content: str) -> List[CodeChunk]:
        """
        Chunk Python code with AST-based function/class extraction
        """
        chunks = []

        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
            return self._chunk_generic(file_path, content)

        lines = content.split("\n")

        # Extract module-level docstring
        module_docstring = ast.get_docstring(tree)
        if module_docstring:
            chunks.append(CodeChunk(
                content=f'"""{module_docstring}"""',
                file_path=file_path,
                start_line=1,
                end_line=module_docstring.count("\n") + 3,
                chunk_type="docstring",
                name="module_docstring",
            ))

        # Extract imports as a chunk
        imports = []
        import_lines = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                import_lines.append(node.lineno)

        if import_lines:
            start = min(import_lines)
            end = max(import_lines)
            import_content = "\n".join(lines[start - 1 : end])
            chunks.append(CodeChunk(
                content=import_content,
                file_path=file_path,
                start_line=start,
                end_line=end,
                chunk_type="imports",
                name="imports",
            ))

        # Extract functions and classes
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                chunk = self._extract_function_chunk(node, lines, file_path)
                if chunk:
                    chunks.append(chunk)

            elif isinstance(node, ast.ClassDef):
                # Extract class-level chunk
                class_chunk = self._extract_class_chunk(node, lines, file_path)
                if class_chunk:
                    chunks.append(class_chunk)

                # Extract methods
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_chunk = self._extract_function_chunk(
                            item, lines, file_path, parent=node.name
                        )
                        if method_chunk:
                            chunks.append(method_chunk)

        # If no functions/classes found, fall back to generic chunking
        if len(chunks) <= 2:  # Only imports and maybe docstring
            return self._chunk_generic(file_path, content)

        return chunks

    def _extract_function_chunk(
        self,
        node: ast.FunctionDef,
        lines: List[str],
        file_path: str,
        parent: Optional[str] = None,
    ) -> Optional[CodeChunk]:
        """Extract a function as a chunk"""
        try:
            start_line = node.lineno
            end_line = node.end_lineno or start_line

            # Include decorators
            if node.decorator_list:
                start_line = min(d.lineno for d in node.decorator_list)

            content = "\n".join(lines[start_line - 1 : end_line])
            docstring = ast.get_docstring(node)

            return CodeChunk(
                content=content,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                chunk_type="method" if parent else "function",
                name=node.name,
                parent=parent,
                docstring=docstring,
            )
        except Exception as e:
            logger.warning(f"Error extracting function {node.name}: {e}")
            return None

    def _extract_class_chunk(
        self,
        node: ast.ClassDef,
        lines: List[str],
        file_path: str,
    ) -> Optional[CodeChunk]:
        """Extract class definition (without methods) as a chunk"""
        try:
            start_line = node.lineno
            
            # Find where class body starts (after docstring and class variables)
            # We want just the class signature and docstring
            end_line = start_line
            
            # Include decorators
            if node.decorator_list:
                start_line = min(d.lineno for d in node.decorator_list)

            # Find end of class signature and docstring
            docstring = ast.get_docstring(node)
            if docstring:
                # Find where docstring ends
                for i, item in enumerate(node.body):
                    if isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant):
                        end_line = item.end_lineno or item.lineno
                        break

            # Get class signature
            class_line = lines[node.lineno - 1]
            signature = f"{class_line}\n"
            if docstring:
                signature += f'    """{docstring}"""\n'

            return CodeChunk(
                content=signature,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                chunk_type="class",
                name=node.name,
                docstring=docstring,
            )
        except Exception as e:
            logger.warning(f"Error extracting class {node.name}: {e}")
            return None

    def _chunk_javascript(self, file_path: str, content: str) -> List[CodeChunk]:
        """
        Chunk JavaScript/TypeScript code with regex-based extraction
        """
        chunks = []
        lines = content.split("\n")

        # Function patterns
        function_patterns = [
            # Regular functions
            r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\([^)]*\)\s*\{",
            # Arrow functions assigned to variables
            r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>",
            # Class methods
            r"(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{",
        ]

        # Class pattern
        class_pattern = r"(?:export\s+)?class\s+(\w+)"

        # Find functions
        for pattern in function_patterns:
            for match in re.finditer(pattern, content):
                func_name = match.group(1)
                start_pos = match.start()
                start_line = content[:start_pos].count("\n") + 1

                # Find matching closing brace
                end_line = self._find_closing_brace(content, match.end() - 1)
                if end_line:
                    func_content = "\n".join(lines[start_line - 1 : end_line])
                    chunks.append(CodeChunk(
                        content=func_content,
                        file_path=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        chunk_type="function",
                        name=func_name,
                    ))

        # Find classes
        for match in re.finditer(class_pattern, content):
            class_name = match.group(1)
            start_pos = match.start()
            start_line = content[:start_pos].count("\n") + 1

            end_line = self._find_closing_brace(content, content.find("{", match.end()))
            if end_line:
                class_content = "\n".join(lines[start_line - 1 : end_line])
                chunks.append(CodeChunk(
                    content=class_content,
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    chunk_type="class",
                    name=class_name,
                ))

        if not chunks:
            return self._chunk_generic(file_path, content)

        return chunks

    def _find_closing_brace(self, content: str, start_pos: int) -> Optional[int]:
        """Find the line number of the matching closing brace"""
        if start_pos < 0 or start_pos >= len(content):
            return None

        brace_count = 0
        in_string = False
        string_char = None

        for i, char in enumerate(content[start_pos:], start=start_pos):
            if char in ('"', "'", "`") and (i == 0 or content[i - 1] != "\\"):
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None

            if not in_string:
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        return content[:i + 1].count("\n") + 1

        return None

    def _chunk_generic(self, file_path: str, content: str) -> List[CodeChunk]:
        """
        Generic chunking based on line count and character count
        """
        chunks = []
        lines = content.split("\n")

        current_chunk_lines = []
        current_chunk_start = 1
        current_size = 0

        for i, line in enumerate(lines, start=1):
            current_chunk_lines.append(line)
            current_size += len(line) + 1  # +1 for newline

            # Check if we should create a chunk
            should_chunk = False
            
            # Chunk at natural boundaries when size is sufficient
            if current_size >= self.chunk_size:
                # Try to chunk at empty lines or logical boundaries
                if not line.strip():  # Empty line
                    should_chunk = True
                elif i == len(lines):  # End of file
                    should_chunk = True
                elif current_size >= self.chunk_size * 1.5:  # Force chunk
                    should_chunk = True

            if should_chunk and current_chunk_lines:
                chunk_content = "\n".join(current_chunk_lines)
                if len(chunk_content.strip()) >= self.min_chunk_size:
                    chunks.append(CodeChunk(
                        content=chunk_content,
                        file_path=file_path,
                        start_line=current_chunk_start,
                        end_line=i,
                        chunk_type="block",
                    ))

                # Start new chunk with overlap
                overlap_lines = int(self.chunk_overlap / 50)  # Approximate lines
                if overlap_lines > 0 and len(current_chunk_lines) > overlap_lines:
                    current_chunk_lines = current_chunk_lines[-overlap_lines:]
                    current_chunk_start = i - overlap_lines + 1
                else:
                    current_chunk_lines = []
                    current_chunk_start = i + 1
                current_size = sum(len(l) + 1 for l in current_chunk_lines)

        # Add remaining content
        if current_chunk_lines:
            chunk_content = "\n".join(current_chunk_lines)
            if len(chunk_content.strip()) >= self.min_chunk_size:
                chunks.append(CodeChunk(
                    content=chunk_content,
                    file_path=file_path,
                    start_line=current_chunk_start,
                    end_line=len(lines),
                    chunk_type="block",
                ))

        return chunks

    def chunk_project(
        self,
        project_path: Path,
        exclude_patterns: Optional[List[str]] = None,
    ) -> List[CodeChunk]:
        """
        Chunk all files in a project

        Args:
            project_path: Path to the project
            exclude_patterns: Patterns to exclude

        Returns:
            List of all code chunks
        """
        exclude = exclude_patterns or [
            ".git", ".venv", "venv", "__pycache__", "node_modules",
            ".idea", ".vscode", "dist", "build", ".agentforge_backups",
        ]

        all_chunks = []

        for file_path in project_path.rglob("*"):
            # Skip excluded directories
            if any(ex in file_path.parts for ex in exclude):
                continue

            if file_path.is_file() and file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                try:
                    content = file_path.read_text(encoding="utf-8")
                    relative_path = str(file_path.relative_to(project_path))
                    chunks = self.chunk_file(relative_path, content)
                    all_chunks.extend(chunks)
                except Exception as e:
                    logger.warning(f"Error chunking {file_path}: {e}")

        logger.info(f"Chunked {len(all_chunks)} chunks from project")
        return all_chunks
