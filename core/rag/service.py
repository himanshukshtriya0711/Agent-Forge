"""
RAG Service
High-level service for indexing projects and retrieving code context
"""

import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from django.conf import settings

from .chunker import CodeChunker, CodeChunk
from .vectorstore import VectorStore
from .retriever import CodeRetriever
from ..llm import GroqClient

logger = logging.getLogger("agentforge.rag")


class RAGService:
    """
    High-level RAG service for code indexing and retrieval
    Coordinates chunking, embedding, storage, and retrieval
    """

    def __init__(
        self,
        project_path: Optional[Path] = None,
        collection_name: Optional[str] = None,
    ):
        """
        Initialize RAG Service

        Args:
            project_path: Path to the project to index
            collection_name: Optional custom collection name
        """
        self.project_path = Path(project_path) if project_path else settings.PROJECTS_DIR
        self.collection_name = collection_name or f"project_{self._get_project_hash()}"

        # Initialize components
        self.chunker = CodeChunker(
            chunk_size=settings.RAG_CHUNK_SIZE,
            chunk_overlap=settings.RAG_CHUNK_OVERLAP,
        )
        self.vector_store = VectorStore(collection_name=self.collection_name)
        self.retriever = CodeRetriever(
            vector_store=self.vector_store,
            top_k=settings.RAG_TOP_K,
        )

        logger.info(f"Initialized RAGService for project: {self.project_path}")

    def _get_project_hash(self) -> str:
        """Generate a short hash from project path for unique collection name"""
        return hashlib.md5(str(self.project_path).encode()).hexdigest()[:8]

    def index_project(
        self,
        force_reindex: bool = False,
        exclude_patterns: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Index the entire project

        Args:
            force_reindex: Clear existing index and reindex
            exclude_patterns: Patterns to exclude from indexing

        Returns:
            Dictionary with indexing results
        """
        try:
            if force_reindex:
                logger.info("Force reindex requested, clearing existing index")
                self.vector_store.clear()

            # Get current stats
            stats = self.vector_store.get_stats()
            if stats["success"] and stats["document_count"] > 0 and not force_reindex:
                logger.info(f"Index already exists with {stats['document_count']} documents")
                return {
                    "success": True,
                    "message": "Index already exists",
                    "document_count": stats["document_count"],
                    "reindexed": False,
                }

            # Chunk the project
            logger.info(f"Chunking project: {self.project_path}")
            chunks = self.chunker.chunk_project(
                self.project_path,
                exclude_patterns=exclude_patterns,
            )

            if not chunks:
                return {
                    "success": True,
                    "message": "No files to index",
                    "document_count": 0,
                }

            # Prepare documents for vector store
            documents = []
            metadatas = []
            ids = []

            for i, chunk in enumerate(chunks):
                chunk_id = f"{chunk.file_path}:{chunk.start_line}:{chunk.end_line}:{i}"
                chunk_hash = hashlib.md5(chunk_id.encode()).hexdigest()

                documents.append(chunk.content)
                metadatas.append({
                    "file_path": chunk.file_path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "chunk_type": chunk.chunk_type,
                    "name": chunk.name or "",
                    "parent": chunk.parent or "",
                })
                ids.append(chunk_hash)

            # Add to vector store
            logger.info(f"Adding {len(documents)} chunks to vector store")
            result = self.vector_store.add_documents(
                documents=documents,
                metadatas=metadatas,
                ids=ids,
            )

            if not result["success"]:
                return result

            return {
                "success": True,
                "message": "Project indexed successfully",
                "document_count": len(documents),
                "files_processed": len(set(c.file_path for c in chunks)),
                "reindexed": True,
            }

        except Exception as e:
            logger.error(f"Error indexing project: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def index_file(self, file_path: str, content: str) -> Dict[str, Any]:
        """
        Index or update a single file

        Args:
            file_path: Path to the file (relative to project)
            content: File content

        Returns:
            Dictionary with indexing result
        """
        try:
            # Remove existing chunks for this file
            self.vector_store.delete(where={"file_path": file_path})

            # Chunk the file
            chunks = self.chunker.chunk_file(file_path, content)

            if not chunks:
                return {
                    "success": True,
                    "message": "No chunks generated",
                    "chunks_added": 0,
                }

            # Prepare documents
            documents = []
            metadatas = []
            ids = []

            for i, chunk in enumerate(chunks):
                chunk_id = f"{chunk.file_path}:{chunk.start_line}:{chunk.end_line}:{i}"
                chunk_hash = hashlib.md5(chunk_id.encode()).hexdigest()

                documents.append(chunk.content)
                metadatas.append({
                    "file_path": chunk.file_path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "chunk_type": chunk.chunk_type,
                    "name": chunk.name or "",
                    "parent": chunk.parent or "",
                })
                ids.append(chunk_hash)

            # Add to vector store
            result = self.vector_store.add_documents(
                documents=documents,
                metadatas=metadatas,
                ids=ids,
            )

            if not result["success"]:
                return result

            return {
                "success": True,
                "file_path": file_path,
                "chunks_added": len(chunks),
            }

        except Exception as e:
            logger.error(f"Error indexing file {file_path}: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def remove_file(self, file_path: str) -> Dict[str, Any]:
        """
        Remove a file from the index

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with result
        """
        return self.vector_store.delete(where={"file_path": file_path})

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant code for a query

        Args:
            query: The search query
            top_k: Number of results

        Returns:
            List of relevant code chunks
        """
        return self.retriever.retrieve(query, top_k)

    def get_context(
        self,
        query: str,
        top_k: Optional[int] = None,
        include_structure: bool = True,
    ) -> str:
        """
        Get formatted context for LLM consumption

        Args:
            query: The search query
            top_k: Number of results
            include_structure: Include project structure

        Returns:
            Formatted context string
        """
        context_parts = []

        # Get relevant code
        code_context = self.retriever.retrieve_with_context(query, top_k)
        context_parts.append("## Relevant Code\n")
        context_parts.append(code_context)

        # Include project structure if requested
        if include_structure:
            from ..tools import FileReader
            reader = FileReader(self.project_path)
            structure = reader.get_project_structure(max_depth=3)
            context_parts.append("\n## Project Structure\n")
            context_parts.append(f"```\n{structure}\n```")

        return "\n".join(context_parts)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the index

        Returns:
            Dictionary with index statistics
        """
        stats = self.vector_store.get_stats()
        stats["project_path"] = str(self.project_path)
        stats["collection_name"] = self.collection_name
        return stats

    def clear_index(self) -> Dict[str, Any]:
        """
        Clear the entire index

        Returns:
            Dictionary with result
        """
        return self.vector_store.clear()
