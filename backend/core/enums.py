from enum import Enum


class CaseStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    closed = "closed"
    archived = "archived"