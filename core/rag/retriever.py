"""
Code Retriever
Retrieves relevant code context using vector similarity search
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from django.conf import settings

from .vectorstore import VectorStore
from .chunker import CodeChunker, CodeChunk

logger = logging.getLogger("agentforge.rag")


class CodeRetriever:
    """
    Retrieves relevant code snippets based on semantic similarity
    """

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        embeddings_model = None,
        top_k: int = 5,
    ):
        """
        Initialize CodeRetriever

        Args:
            vector_store: VectorStore instance
            embeddings_model: Model for generating embeddings
            top_k: Default number of results to retrieve
        """
        self.vector_store = vector_store or VectorStore()
        self.embeddings_model = embeddings_model
        self.top_k = top_k or settings.RAG_TOP_K

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        file_filter: Optional[List[str]] = None,
        chunk_type_filter: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant code chunks for a query

        Args:
            query: The search query
            top_k: Number of results to return
            file_filter: Filter by file paths
            chunk_type_filter: Filter by chunk types

        Returns:
            List of relevant code chunks with metadata
        """
        top_k = top_k or self.top_k

        # Build where filter
        where = None
        if file_filter:
            where = {"file_path": {"$in": file_filter}}
        elif chunk_type_filter:
            where = {"chunk_type": {"$in": chunk_type_filter}}

        # Query vector store
        results = self.vector_store.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
        )

        if not results["success"]:
            logger.error(f"Retrieval error: {results.get('error')}")
            return []

        # Format results
        formatted = []
        for result in results["results"]:
            formatted.append({
                "content": result["document"],
                "file_path": result["metadata"].get("file_path", ""),
                "start_line": result["metadata"].get("start_line", 0),
                "end_line": result["metadata"].get("end_line", 0),
                "chunk_type": result["metadata"].get("chunk_type", ""),
                "name": result["metadata"].get("name", ""),
                "similarity": 1 - result["distance"] if result["distance"] else 0,
            })

        return formatted

    def retrieve_with_context(
        self,
        query: str,
        top_k: Optional[int] = None,
        context_lines: int = 5,
    ) -> str:
        """
        Retrieve code and format it as context for LLM

        Args:
            query: The search query
            top_k: Number of results
            context_lines: Additional context lines to include

        Returns:
            Formatted context string
        """
        results = self.retrieve(query, top_k)

        if not results:
            return "No relevant code found in the project."

        context_parts = []
        for i, result in enumerate(results, 1):
            part = f"""
### Result {i}: {result['file_path']}
**Type:** {result['chunk_type']} | **Name:** {result.get('name', 'N/A')} | **Lines:** {result['start_line']}-{result['end_line']}
**Similarity:** {result['similarity']:.2%}

```
{result['content']}
```
"""
            context_parts.append(part)

        return "\n".join(context_parts)

    def retrieve_for_file(
        self,
        file_path: str,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve other relevant code for a specific file

        Args:
            file_path: Path to the file
            top_k: Number of results

        Returns:
            List of related code chunks
        """
        # First, get chunks from the target file as context
        file_results = self.vector_store.query(
            query_texts=[f"code in {file_path}"],
            n_results=1,
            where={"file_path": file_path},
        )

        if not file_results["success"] or not file_results["results"]:
            return []

        # Use the file's content to find related code
        file_content = file_results["results"][0]["document"]
        
        # Search for related code excluding the same file
        return self.retrieve(
            query=file_content[:500],  # Use first 500 chars as query
            top_k=top_k,
        )

    def find_similar_functions(
        self,
        function_name: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Find functions similar to the given function name

        Args:
            function_name: Name of the function
            top_k: Number of results

        Returns:
            List of similar functions
        """
        return self.retrieve(
            query=f"function {function_name}",
            top_k=top_k,
            chunk_type_filter=["function", "method"],
        )

    def get_file_overview(self, file_path: str) -> Dict[str, Any]:
        """
        Get an overview of a file's contents from the index

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with file overview
        """
        results = self.vector_store.query(
            query_texts=[file_path],
            n_results=20,  # Get many chunks to cover the file
            where={"file_path": file_path},
        )

        if not results["success"]:
            return {
                "success": False,
                "error": results.get("error"),
            }

        chunks = results["results"]
        
        # Organize chunks by type
        functions = []
        classes = []
        other = []

        for chunk in chunks:
            metadata = chunk["metadata"]
            info = {
                "name": metadata.get("name", ""),
                "start_line": metadata.get("start_line", 0),
                "end_line": metadata.get("end_line", 0),
            }
            
            chunk_type = metadata.get("chunk_type", "")
            if chunk_type in ("function", "method"):
                functions.append(info)
            elif chunk_type == "class":
                classes.append(info)
            else:
                other.append(info)

        return {
            "success": True,
            "file_path": file_path,
            "functions": functions,
            "classes": classes,
            "other_chunks": other,
            "total_chunks": len(chunks),
        }
