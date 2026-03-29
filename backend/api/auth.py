from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.deps import get_db, get_current_user
from backend.core.hashing import hash_password, verify_password
from backend.core.jwt_handler import create_access_token
from backend.models.user import User
from backend.models.tenant import Tenant
from backend.api.user_schema import UserRegister, UserLogin, UserOut, Token

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    normalized_email = user_data.email.lower().strip()

    existing_user = db.query(User).filter(
        User.email == normalized_email,
        User.deleted_at.is_(None)
    ).first()

    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    tenant = db.query(Tenant).filter(Tenant.name == user_data.tenant_name).first()

    if not tenant:
        tenant = Tenant(name=user_data.tenant_name)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

    new_user = User(
        name=user_data.name.strip(),
        email=normalized_email,
        hashed_password=hash_password(user_data.password),
        role=user_data.role,
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


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
