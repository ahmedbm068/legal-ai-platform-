from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.deps import get_db, get_current_user
from backend.core.permissions import apply_tenant_scope
from backend.models.user import User
from backend.api.user_schema import UserOut

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(User).filter(User.deleted_at.is_(None))
    return apply_tenant_scope(query, User.tenant_id, current_user).all()