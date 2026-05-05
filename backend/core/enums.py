from enum import Enum


class UserRole(str, Enum):
    admin = "admin"
    lawyer = "lawyer"
    client = "client"
    assistant = "assistant"


class CaseStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    closed = "closed"
    archived = "archived"


class JurisdictionCountry(str, Enum):
    tunisia = "tunisia"
    germany = "germany"
