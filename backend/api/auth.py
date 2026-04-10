from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.deps import get_db, get_current_user
from backend.core.enums import UserRole
from backend.core.hashing import hash_password, verify_password
from backend.core.jwt_handler import create_access_token
from backend.core.permissions import require_roles
from backend.core.tenants import slugify_tenant_name
from backend.models.staff_invite import StaffInvite
from backend.models.user import User
from backend.models.tenant import Tenant
from backend.api.user_schema import StaffInviteCreate, StaffInviteOut, UserRegister, UserLogin, UserOut, Token

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _resolve_bootstrap_tenant(db: Session, tenant_name: str | None) -> Tenant:
    normalized_tenant_name = str(tenant_name or "").strip()
    if not normalized_tenant_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tenant_name is required for the initial bootstrap registration.",
        )

    tenant = db.query(Tenant).filter(Tenant.name == normalized_tenant_name).first()
    if tenant:
        if not tenant.slug:
            tenant.slug = slugify_tenant_name(tenant.name)
            db.commit()
            db.refresh(tenant)
        return tenant

    tenant = Tenant(
        name=normalized_tenant_name,
        slug=slugify_tenant_name(normalized_tenant_name),
        portal_access_enabled=True,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def _resolve_invited_registration(
    *,
    db: Session,
    normalized_email: str,
    invite_token: str | None,
) -> tuple[Tenant, UserRole]:
    if settings.STAFF_INVITE_ONLY and not invite_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff registration requires a valid invite token.",
        )

    invite: StaffInvite | None = None
    if invite_token:
        invite = (
            db.query(StaffInvite)
            .filter(
                StaffInvite.invite_token == invite_token.strip(),
                StaffInvite.used_at.is_(None),
            )
            .first()
        )

    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired invite token.",
        )

    if invite.email.strip().lower() != normalized_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invite token email does not match the registration email.",
        )

    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invite token has expired.",
        )

    tenant = db.query(Tenant).filter(Tenant.id == invite.tenant_id).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Invite tenant not found.")

    role_value = invite.role.value if hasattr(invite.role, "value") else str(invite.role)
    resolved_role = UserRole(role_value)
    invite.used_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(tenant)
    return tenant, resolved_role


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    normalized_email = user_data.email.lower().strip()

    existing_user = db.query(User).filter(
        User.email == normalized_email,
        User.deleted_at.is_(None)
    ).first()

    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    active_user_count = db.query(User).filter(User.deleted_at.is_(None)).count()
    if active_user_count == 0:
        tenant = _resolve_bootstrap_tenant(db, user_data.tenant_name)
        resolved_role = user_data.role
    else:
        tenant, resolved_role = _resolve_invited_registration(
            db=db,
            normalized_email=normalized_email,
            invite_token=user_data.invite_token,
        )

    new_user = User(
        name=user_data.name.strip(),
        email=normalized_email,
        hashed_password=hash_password(user_data.password),
        role=resolved_role,
        tenant_id=tenant.id
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.post("/login", response_model=Token)
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    normalized_email = user_data.email.lower().strip()

    user = db.query(User).filter(
        User.email == normalized_email,
        User.deleted_at.is_(None)
    ).first()

    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "tenant_id": user.tenant_id,
            "role": user.role.value if hasattr(user.role, "value") else user.role
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.post("/invites", response_model=StaffInviteOut, status_code=status.HTTP_201_CREATED)
def create_staff_invite(
    data: StaffInviteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, [UserRole.admin])

    invite = StaffInvite(
        tenant_id=current_user.tenant_id,
        created_by_user_id=current_user.id,
        email=data.email.lower().strip(),
        role=data.role.value if hasattr(data.role, "value") else str(data.role),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=int(data.expires_hours)),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
