from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from backend.core.permissions import apply_tenant_scope, require_roles
from backend.core.deps import get_db, get_current_user
from backend.core.enums import UserRole
from backend.models.user import User
from backend.models.client import Client
from backend.api.client_schema import ClientCreate, ClientUpdate, ClientOut

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.post("/", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(
    client_data: ClientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_roles(current_user, [UserRole.admin, UserRole.lawyer])

    normalized_phone = client_data.phone.strip()
    if not normalized_phone:
        raise HTTPException(status_code=400, detail="Client phone number is required")

    new_client = Client(
        name=client_data.name,
        email=client_data.email,
        phone=normalized_phone,
        address=client_data.address,
        tenant_id=current_user.tenant_id
    )

    db.add(new_client)
    db.commit()
    db.refresh(new_client)

    return new_client


@router.get("/", response_model=list[ClientOut])
def list_clients(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Client).filter(Client.deleted_at.is_(None))
    clients = apply_tenant_scope(query, Client.tenant_id, current_user).all()

    return clients


@router.get("/{client_id}", response_model=ClientOut)
def get_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Client).filter(
        Client.id == client_id,
        Client.deleted_at.is_(None)
    )
    client = apply_tenant_scope(query, Client.tenant_id, current_user).first()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    return client


@router.put("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: int,
    client_data: ClientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_roles(current_user, [UserRole.admin, UserRole.lawyer])

    query = db.query(Client).filter(
        Client.id == client_id,
        Client.deleted_at.is_(None)
    )
    client = apply_tenant_scope(query, Client.tenant_id, current_user).first()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if client_data.name is not None:
        client.name = client_data.name

    if client_data.email is not None:
        client.email = client_data.email

    if client_data.phone is not None:
        client.phone = client_data.phone

    if client_data.address is not None:
        client.address = client_data.address

    db.commit()
    db.refresh(client)

    return client


@router.delete("/{client_id}", status_code=status.HTTP_200_OK)
def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_roles(current_user, [UserRole.admin])

    query = db.query(Client).filter(
        Client.id == client_id,
        Client.deleted_at.is_(None)
    )
    client = apply_tenant_scope(query, Client.tenant_id, current_user).first()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    client.deleted_at = func.now()
    db.commit()

    return {"message": "Client archived successfully"}
