from fastapi import HTTPException, status
from backend.models.user import User
from backend.core.enums import UserRole


def is_admin(current_user: User) -> bool:
    role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    return role == UserRole.admin.value


def apply_tenant_scope(query, tenant_column, current_user: User):
    if is_admin(current_user):
        return query
    return query.filter(tenant_column == current_user.tenant_id)


def require_roles(current_user: User, allowed_roles: list[UserRole]):
    """
    Check if the current user has one of the allowed roles.
    """

    if is_admin(current_user):
        return

    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action"
        )