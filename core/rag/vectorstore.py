"""
Vector Store
ChromaDB-based vector store for code embeddings
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings
from django.conf import settings

logger = logging.getLogger("agentforge.rag")


class VectorStore:
    """
    ChromaDB-based vector store for storing and retrieving code embeddings
    """

    def __init__(
        self,
        collection_name: Optional[str] = None,
        persist_directory: Optional[Path] = None,
    ):
        """
        Initialize VectorStore

        Args:
            collection_name: Name of the collection
            persist_directory: Directory to persist the database
        """
        self.collection_name = collection_name or settings.CHROMA_COLLECTION_NAME
        self.persist_directory = persist_directory or settings.CHROMA_PERSIST_DIR

        # Ensure persist directory exists
        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        logger.info(
            f"Initialized VectorStore: collection={self.collection_name}, "
            f"persist_dir={self.persist_directory}"
        )

    def add_documents(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        ids: List[str],
        embeddings: Optional[List[List[float]]] = None,
    ) -> Dict[str, Any]:
        """
        Add documents to the vector store

        Args:
            documents: List of document texts
            metadatas: List of metadata dicts
            ids: List of unique IDs
            embeddings: Optional pre-computed embeddings

        Returns:
            Dictionary with operation result
        """
        try:
            if embeddings:
                self.collection.add(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids,
                    embeddings=embeddings,
                )
            else:
                self.collection.add(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids,
                )

            logger.info(f"Added {len(documents)} documents to vector store")

            return {
                "success": True,
                "documents_added": len(documents),
            }

        except Exception as e:
            logger.error(f"Error adding documents: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def query(
        self,
        query_texts: Optional[List[str]] = None,
        query_embeddings: Optional[List[List[float]]] = None,
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Query the vector store

        Args:
            query_texts: List of query texts
            query_embeddings: Optional pre-computed query embeddings
            n_results: Number of results to return
            where: Filter on metadata
            where_document: Filter on document content

        Returns:
            Dictionary with query results
        """
        try:
            kwargs = {
                "n_results": n_results,
                "include": ["documents", "metadatas", "distances"],
            }

            if query_texts:
                kwargs["query_texts"] = query_texts
            elif query_embeddings:
                kwargs["query_embeddings"] = query_embeddings
            else:
                return {
                    "success": False,
                    "error": "Either query_texts or query_embeddings required",
                }

            if where:
                kwargs["where"] = where
            if where_document:
                kwargs["where_document"] = where_document

            results = self.collection.query(**kwargs)

            # Format results
            formatted_results = []
            if results["documents"]:
                for i, doc_list in enumerate(results["documents"]):
                    for j, doc in enumerate(doc_list):
                        formatted_results.append({
                            "document": doc,
                            "metadata": results["metadatas"][i][j] if results["metadatas"] else {},
                            "distance": results["distances"][i][j] if results["distances"] else None,
                            "id": results["ids"][i][j] if results["ids"] else None,
                        })

            return {
                "success": True,
                "results": formatted_results,
                "count": len(formatted_results),
            }

        except Exception as e:
            logger.error(f"Error querying vector store: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def delete(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Delete documents from the vector store

        Args:
            ids: List of IDs to delete
            where: Filter condition for deletion

        Returns:
            Dictionary with operation result
        """
        try:
            if ids:
                self.collection.delete(ids=ids)
            elif where:
                self.collection.delete(where=where)
            else:
                return {
                    "success": False,
                    "error": "Either ids or where filter required",
                }

            logger.info(f"Deleted documents from vector store")

            return {
                "success": True,
            }

        except Exception as e:
            logger.error(f"Error deleting documents: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def update(
        self,
        ids: List[str],
        documents: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
        embeddings: Optional[List[List[float]]] = None,
    ) -> Dict[str, Any]:
        """
        Update documents in the vector store

        Args:
            ids: List of IDs to update
            documents: New document texts
            metadatas: New metadata dicts
            embeddings: New embeddings

        Returns:
            Dictionary with operation result
        """
        try:
            kwargs = {"ids": ids}
            if documents:
                kwargs["documents"] = documents
            if metadatas:
                kwargs["metadatas"] = metadatas
            if embeddings:
                kwargs["embeddings"] = embeddings

            self.collection.update(**kwargs)

            return {
                "success": True,
                "documents_updated": len(ids),
            }

        except Exception as e:
            logger.error(f"Error updating documents: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the vector store

        Returns:
            Dictionary with store statistics
        """
        try:
            count = self.collection.count()
            
            return {
                "success": True,
                "collection_name": self.collection_name,
                "document_count": count,
                "persist_directory": str(self.persist_directory),
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def clear(self) -> Dict[str, Any]:
        """
        Clear all documents from the collection

        Returns:
            Dictionary with operation result
        """
        try:
            # Delete and recreate collection
            self.client.delete_collection(self.collection_name)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )

            logger.info(f"Cleared collection: {self.collection_name}")

            return {
                "success": True,
                "message": "Collection cleared",
            }

        except Exception as e:
            logger.error(f"Error clearing collection: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def get_by_ids(self, ids: List[str]) -> Dict[str, Any]:
        """
        Get documents by their IDs

        Args:
            ids: List of document IDs

        Returns:
            Dictionary with documents and metadata
        """
        try:
            results = self.collection.get(
                ids=ids,
                include=["documents", "metadatas"],
            )

            documents = []
            for i, doc in enumerate(results["documents"] or []):
                documents.append({
                    "id": results["ids"][i],
                    "document": doc,
                    "metadata": results["metadatas"][i] if results["metadatas"] else {},
                })

            return {
                "success": True,
                "documents": documents,
                "count": len(documents),
            }

        except Exception as e:
            logger.error(f"Error getting documents by ID: {e}")
            return {
                "success": False,
                "error": str(e),
            }
