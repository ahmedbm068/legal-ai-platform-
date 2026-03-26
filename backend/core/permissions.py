from fastapi import HTTPException, status
from backend.models.user import User


def require_roles(current_user: User, allowed_roles: list[str]):
    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action"
        )