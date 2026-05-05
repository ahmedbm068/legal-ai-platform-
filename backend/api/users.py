from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.deps import get_db
from backend.core.permissions import apply_tenant_scope, require_admin
from backend.models.user import User
from backend.api.user_schema import UserOut

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):

    query = db.query(User).filter(User.deleted_at.is_(None))
    users = apply_tenant_scope(query, User.tenant_id, current_user).all()

    return users
