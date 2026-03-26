from fastapi import HTTPException, status
from backend.models.user import User
from backend.core.enums import UserRole


def require_roles(current_user: User, allowed_roles: list[UserRole]):
    """
    Check if the current user has one of the allowed roles.
    """

    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action"
        )