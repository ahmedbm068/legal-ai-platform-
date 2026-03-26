from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from backend.database.database import Base


class DocumentEntity(Base):
    __tablename__ = "document_entities"

    id = Column(Integer, primary_key=True, index=True)

    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    label = Column(String, nullable=False, index=True)
    value = Column(String, nullable=False)

    start_char = Column(Integer, nullable=True)
    end_char = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document = relationship("Document", back_populates="entities")