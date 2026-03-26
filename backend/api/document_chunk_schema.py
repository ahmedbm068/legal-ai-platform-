from pydantic import BaseModel, ConfigDict
from datetime import datetime


class DocumentChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    case_id: int
    chunk_index: int
    content: str
    created_at: datetime