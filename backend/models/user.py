from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import Enum as SQLAlchemyEnum

from backend.database.database import Base
from backend.core.enums import UserRole


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)

    email = Column(String, unique=True, index=True, nullable=False)

    hashed_password = Column(String, nullable=False)

    role = Column(
        SQLAlchemyEnum(UserRole),
        nullable=False,
        default=UserRole.lawyer
    )

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    deleted_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant", back_populates="users")

    cases = relationship("Case", back_populates="lawyer")