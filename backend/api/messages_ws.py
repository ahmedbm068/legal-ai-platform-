"""WebSocket endpoints for real-time case messaging.

Two endpoints, both joining the same per-case room so staff and portal
see each other's events instantly:

* ``/ws/staff/messages/{case_id}?token=<staff JWT>``
* ``/ws/portal/messages/{case_id}?token=<portal JWT>``

Tokens are passed as a query param because browsers cannot set custom
headers on the WebSocket handshake. The same JWT secrets/audience rules
as the REST auth deps are applied here.

Client -> server events: ``{"type": "typing"}``, ``{"type": "ping"}``.
Server -> client events: ``{"type": "message", ...}``,
``{"type": "typing", "role": "..."}``, ``{"type": "pong"}``.
Message creation itself stays on the REST endpoints (multipart uploads,
validation); those handlers broadcast the created message here.
"""
from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.jwt_handler import ALGORITHM, SECRET_KEY as STAFF_SECRET_KEY
from backend.core.permissions import apply_tenant_scope
from backend.core.ws_manager import room_manager
from backend.database.database import SessionLocal
from backend.models.case import Case
from backend.models.client_portal_account import ClientPortalAccount
from backend.models.user import User

router = APIRouter(tags=["Realtime Messaging"])

PORTAL_TOKEN_AUDIENCE = "client_portal"


def _staff_user_for_case(token: str, case_id: int) -> User | None:
    """Validate a staff JWT and confirm the user can see ``case_id``."""
    try:
        payload = jwt.decode(token, STAFF_SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        return None

    db: Session = SessionLocal()
    try:
        user = (
            db.query(User)
            .filter(User.id == user_id, User.deleted_at.is_(None))
            .first()
        )
        if not user:
            return None
        query = db.query(Case).filter(Case.id == case_id, Case.deleted_at.is_(None))
        case = apply_tenant_scope(query, Case.tenant_id, user).first()
        return user if case else None
    finally:
        db.close()


def _portal_account_for_case(token: str, case_id: int) -> ClientPortalAccount | None:
    """Validate a portal JWT and confirm the account can see ``case_id``."""
    try:
        payload = jwt.decode(
            token,
            settings.PORTAL_SECRET_KEY or STAFF_SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=PORTAL_TOKEN_AUDIENCE,
        )
        if payload.get("account_type") != "client_portal":
            return None
        account_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        return None

    db: Session = SessionLocal()
    try:
        account = (
            db.query(ClientPortalAccount)
            .filter(ClientPortalAccount.id == account_id)
            .first()
        )
        if not account or not account.client_id:
            return None
        case = (
            db.query(Case.id)
            .filter(
                Case.id == case_id,
                Case.client_id == account.client_id,
                Case.tenant_id == account.tenant_id,
                Case.deleted_at.is_(None),
            )
            .first()
        )
        return account if case else None
    finally:
        db.close()


async def _serve(websocket: WebSocket, case_id: int, role: str) -> None:
    """Shared connection lifecycle once auth has passed."""
    await room_manager.connect(case_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            kind = data.get("type")
            if kind == "ping":
                await websocket.send_json({"type": "pong"})
            elif kind == "typing":
                await room_manager.broadcast(
                    case_id,
                    {"type": "typing", "role": role},
                    exclude=websocket,
                )
            # message creation is REST-only; ignore other inbound types
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await room_manager.disconnect(case_id, websocket)


@router.websocket("/ws/staff/messages/{case_id}")
async def staff_messages_ws(
    websocket: WebSocket,
    case_id: int,
    token: str = Query(...),
):
    user = _staff_user_for_case(token, case_id)
    if user is None:
        await websocket.close(code=4401)
        return
    await _serve(websocket, case_id, role="lawyer")


@router.websocket("/ws/portal/messages/{case_id}")
async def portal_messages_ws(
    websocket: WebSocket,
    case_id: int,
    token: str = Query(...),
):
    account = _portal_account_for_case(token, case_id)
    if account is None:
        await websocket.close(code=4401)
        return
    await _serve(websocket, case_id, role="client")
