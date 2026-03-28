from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class ClientPortalLoginCode(Base):
    __tablename__ = "client_portal_login_codes"

    id = Column(Integer, primary_key=True, index=True)

    portal_account_id = Column(
        Integer,
        ForeignKey("client_portal_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email = Column(String, nullable=False, index=True)
    code = Column(String(6), nullable=False)
    purpose = Column(String, nullable=False, default="login")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    delivery_status = Column(String, nullable=False, default="pending")
    delivery_error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    portal_account = relationship("ClientPortalAccount")
