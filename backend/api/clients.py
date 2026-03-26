from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from backend.core.permissions import require_roles
from backend.core.deps import get_db, get_current_user
from backend.models.user import User
from backend.models.client import Client
from backend.api.client_schema import ClientCreate, ClientUpdate, ClientOut

router = APIRouter(prefix="/clients", tags=["Clients"])


# CREATE CLIENT
@router.post("/", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(
    client_data: ClientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_roles(current_user, ["admin", "lawyer"])

    new_client = Client(
        name=client_data.name,
        email=client_data.email,
        phone=client_data.phone,
        address=client_data.address,
        tenant_id=current_user.tenant_id
    )

    db.add(new_client)
    db.commit()
    db.refresh(new_client)

    return new_client


# LIST CLIENTS
@router.get("/", response_model=list[ClientOut])
def list_clients(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    clients = db.query(Client).filter(
        Client.tenant_id == current_user.tenant_id,
        Client.deleted_at == None
    ).all()

    return clients


# GET CLIENT
@router.get("/{client_id}", response_model=ClientOut)
def get_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    client = db.query(Client).filter(
        Client.id == client_id,
        Client.tenant_id == current_user.tenant_id,
        Client.deleted_at == None
    ).first()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    return client


# UPDATE CLIENT
@router.put("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: int,
    client_data: ClientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_roles(current_user, ["admin", "lawyer"])

    client = db.query(Client).filter(
        Client.id == client_id,
        Client.tenant_id == current_user.tenant_id,
        Client.deleted_at == None
    ).first()

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


# DELETE CLIENT (SOFT DELETE)
@router.delete("/{client_id}")
def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    require_roles(current_user, ["admin"])

    client = db.query(Client).filter(
        Client.id == client_id,
        Client.tenant_id == current_user.tenant_id,
        Client.deleted_at == None
    ).first()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    client.deleted_at = func.now()

    db.commit()

    return {"message": "Client archived successfully"}