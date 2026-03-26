from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String, nullable=False, index=True)

    description = Column(Text, nullable=True)

    status = Column(String, nullable=False, default="open")

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)

    lawyer_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    deleted_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant", back_populates="cases")

    lawyer = relationship("User", back_populates="cases")

    client = relationship("Client", back_populates="cases")