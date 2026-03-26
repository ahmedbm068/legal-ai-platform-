from pydantic import BaseModel, ConfigDict
from datetime import datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    storage_path: str
    file_size: int
    file_type: str
    upload_timestamp: datetime
    case_id: int
    tenant_id: int