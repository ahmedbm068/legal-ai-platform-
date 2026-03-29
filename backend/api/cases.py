from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from backend.core.permissions import require_roles
from backend.core.deps import get_db, get_current_user
from backend.core.enums import UserRole
from backend.models.case import Case
from backend.models.user import User
from backend.models.client import Client
from backend.api.case_schema import CaseCreate, CaseUpdate, CaseOut

router = APIRouter(prefix="/cases", tags=["Cases"])


@router.post("/", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
def create_case(
    case_data: CaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_roles(current_user, [UserRole.admin, UserRole.lawyer])

    client = db.query(Client).filter(
        Client.id == case_data.client_id,
        Client.tenant_id == current_user.tenant_id,
        Client.deleted_at.is_(None)
    ).first()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    new_case = Case(
        title=case_data.title,
        description=case_data.description,
        status=case_data.status,
        tenant_id=current_user.tenant_id,
        lawyer_id=current_user.id,
        client_id=case_data.client_id
    )

    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    return new_case


@router.get("/", response_model=list[CaseOut])
def list_cases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(Case).filter(
        Case.tenant_id == current_user.tenant_id,
        Case.deleted_at.is_(None)
    ).all()


@router.get("/{case_id}", response_model=CaseOut)
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    case = db.query(Case).filter(
        Case.id == case_id,
        Case.tenant_id == current_user.tenant_id,
        Case.deleted_at.is_(None)
    ).first()

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    return case


@router.put("/{case_id}", response_model=CaseOut)
def update_case(
    case_id: int,
    case_data: CaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_roles(current_user, [UserRole.admin, UserRole.lawyer])

    case = db.query(Case).filter(
        Case.id == case_id,
        Case.tenant_id == current_user.tenant_id,
        Case.deleted_at.is_(None)
    ).first()

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if current_user.role != UserRole.admin and case.lawyer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your assigned cases"
        )

    if case_data.client_id is not None:
        client = db.query(Client).filter(
            Client.id == case_data.client_id,
            Client.tenant_id == current_user.tenant_id,
            Client.deleted_at.is_(None)
        ).first()

        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        case.client_id = case_data.client_id

    if case_data.title is not None:
        case.title = case_data.title

    if case_data.description is not None:
        case.description = case_data.description

    if case_data.status is not None:
        case.status = case_data.status

    db.commit()
    db.refresh(case)

    return case


@router.delete("/{case_id}", status_code=status.HTTP_200_OK)
def delete_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_roles(current_user, [UserRole.admin, UserRole.lawyer])

    case = db.query(Case).filter(
        Case.id == case_id,
        Case.tenant_id == current_user.tenant_id,
        Case.deleted_at.is_(None)
    ).first()

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if current_user.role != UserRole.admin and case.lawyer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your assigned cases"
        )

    case.deleted_at = func.now()
    db.commit()

    return {"message": "Case archived successfully"}
