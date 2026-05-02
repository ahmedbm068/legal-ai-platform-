from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class CalendarReminder(Base):
    __tablename__ = "calendar_reminders"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(Integer, ForeignKey("calendar_events.id", ondelete="CASCADE"), nullable=False, index=True)
    remind_at = Column(DateTime(timezone=True), nullable=False, index=True)
    method = Column(String, nullable=False, default="in_app")
    status = Column(String, nullable=False, default="pending", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    event = relationship("CalendarEvent", back_populates="reminders")
    tenant = relationship("Tenant")
