from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class CaseMessage(Base):
    """A single message in the client <-> lawyer thread for a case.

    The "thread" is the case itself: a client talks to the lawyer assigned to
    their case. ``sender_role`` distinguishes who wrote the message so the UI
    can render client bubbles vs. counsel bubbles. Attachments are stored
    inline (single optional file per message) to keep the surface small.
    """

    __tablename__ = "case_messages"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, nullable=False, index=True)
    case_id = Column(
        Integer,
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Exactly one of these identifies the author, depending on sender_role.
    portal_account_id = Column(
        Integer,
        ForeignKey("client_portal_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sender_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # "client" | "lawyer"
    sender_role = Column(String(16), nullable=False, index=True)
    sender_name = Column(String, nullable=True)

    body = Column(Text, nullable=False, default="")

    # Optional single attachment, stored on disk like other portal uploads.
    attachment_filename = Column(String, nullable=True)
    attachment_path = Column(String, nullable=True)
    attachment_content_type = Column(String, nullable=True)
    attachment_size = Column(BigInteger, nullable=True)

    # Set when the *other* party has read it. We only need a coarse read
    # marker per side; the client UI cares about lawyer messages it hasn't
    # seen yet, so client-unread = lawyer messages with read_at IS NULL.
    read_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    case = relationship("Case")
    portal_account = relationship("ClientPortalAccount")
    sender_user = relationship("User")
