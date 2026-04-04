from fastapi import HTTPException, status
from backend.models.user import User
from backend.core.enums import UserRole


def _normalized_role_value(value) -> str:
    if hasattr(value, "value"):
        return str(value.value).strip().lower()
    return str(value).strip().lower()


def is_admin(current_user: User) -> bool:
    role = _normalized_role_value(current_user.role)
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

    current_role_value = _normalized_role_value(current_user.role)
    allowed_role_values = {_normalized_role_value(role) for role in allowed_roles}

    if current_role_value not in allowed_role_values:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action"
        )