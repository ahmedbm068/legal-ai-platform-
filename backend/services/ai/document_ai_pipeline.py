import os

from sqlalchemy.orm import Session

from backend.models.document import Document
from backend.services.ai.extraction_service import extract_text_from_pdf
from backend.services.ai.chunking_service import chunk_text
from backend.services.ai.embedding_service import EmbeddingService
from backend.services.ai.vector_store import VectorStore
from backend.services.storage_service import download_file_to_temp


class DocumentAIPipeline:
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStore(dimension=384)

    def process_document(self, document: Document):
        temp_file_path = download_file_to_temp(document.storage_path)

        try:
            text = extract_text_from_pdf(temp_file_path)

            if not text:
                return {
                    "success": False,
                    "message": "No text could be extracted from the PDF."
                }

            chunks = chunk_text(text)
            embeddings = self.embedding_service.embed_texts(chunks)

            metadatas = []
            for i, chunk in enumerate(chunks):
                metadatas.append({
                    "document_id": document.id,
                    "case_id": document.case_id,
                    "filename": document.filename,
                    "chunk_index": i,
                    "chunk_text": chunk,
                })

            self.vector_store.add_embeddings(embeddings, metadatas)

            return {
                "success": True,
                "message": "Document processed successfully.",
                "chunks_count": len(chunks)
            }

        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)