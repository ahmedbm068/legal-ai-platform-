from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from backend.database.database import Base


class Document(Base):

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)

    filename = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)

    file_size = Column(Integer, nullable=False)
    file_type = Column(String, nullable=False)
    upload_timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)