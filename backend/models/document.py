from sqlalchemy import Column, Integer, String, ForeignKey
from backend.database.database import Base


class Document(Base):

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)

    filename = Column(String, nullable=False)

    storage_path = Column(String, nullable=False)

    case_id = Column(Integer, ForeignKey("cases.id"))

    tenant_id = Column(Integer, ForeignKey("tenants.id"))