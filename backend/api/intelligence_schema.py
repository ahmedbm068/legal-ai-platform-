from typing import List, Optional

from pydantic import BaseModel


class EntityOut(BaseModel):
    label: str
    value: str
    start_char: Optional[int] = None
    end_char: Optional[int] = None

    class Config:
        from_attributes = True


class ProcessDocumentResponse(BaseModel):
    document_id: int
    extracted_text_length: int
    entities: List[EntityOut]
    redacted_preview: str
    status: str
    pii_items_count: int


class SearchResultItem(BaseModel):
    document_id: int
    filename: str
    matched_text: str


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResultItem]