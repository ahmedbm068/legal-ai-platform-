from fastapi import Depends, HTTPException, status
from backend.core.deps import get_current_user
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


# ── Route-scoping Depends factories ──────────────────────────────────────────
# Usage:  current_user: User = Depends(require_lawyer)
#         current_user: User = Depends(require_client)
#         current_user: User = Depends(require_admin)

def _role_guard(*allowed: UserRole):
    """Return a FastAPI dependency that enforces role membership."""
    def _dep(current_user: User = Depends(get_current_user)) -> User:
        require_roles(current_user, list(allowed))
        return current_user
    return _dep


require_lawyer = _role_guard(UserRole.lawyer)
require_client = _role_guard(UserRole.client)
require_admin  = _role_guard(UserRole.admin)
require_staff  = _role_guard(UserRole.lawyer, UserRole.assistant)  # lawyer or assistant
