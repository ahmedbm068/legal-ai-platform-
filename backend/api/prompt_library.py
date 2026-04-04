from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.api.prompt_library_schema import PromptLibraryCreate, PromptLibraryOut, PromptLibraryUpdate
from backend.core.deps import get_current_user, get_db
from backend.core.permissions import apply_tenant_scope
from backend.models.prompt_library_entry import PromptLibraryEntry
from backend.models.user import User


router = APIRouter(prefix="/prompt-library", tags=["Prompt Library"])


def _get_entry_or_404(*, db: Session, entry_id: int, current_user: User) -> PromptLibraryEntry:
    query = db.query(PromptLibraryEntry).filter(PromptLibraryEntry.id == entry_id)
    entry = apply_tenant_scope(query, PromptLibraryEntry.tenant_id, current_user).first()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt library entry not found.")
    return entry


@router.get("/", response_model=list[PromptLibraryOut])
def list_prompt_library(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(PromptLibraryEntry).order_by(
        PromptLibraryEntry.is_favorite.desc(),
        PromptLibraryEntry.updated_at.desc(),
        PromptLibraryEntry.id.desc(),
    )
    return apply_tenant_scope(query, PromptLibraryEntry.tenant_id, current_user).all()


@router.post("/", response_model=PromptLibraryOut, status_code=status.HTTP_201_CREATED)
def create_prompt_library_entry(
    payload: PromptLibraryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = PromptLibraryEntry(
        tenant_id=current_user.tenant_id,
        created_by_user_id=current_user.id,
        title=payload.title,
        prompt_text=payload.prompt_text,
        description=payload.description,
        category=payload.category,
        is_favorite=payload.is_favorite,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/{entry_id}", response_model=PromptLibraryOut)
def update_prompt_library_entry(
    entry_id: int,
    payload: PromptLibraryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = _get_entry_or_404(db=db, entry_id=entry_id, current_user=current_user)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(entry, key, value)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prompt_library_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = _get_entry_or_404(db=db, entry_id=entry_id, current_user=current_user)
    db.delete(entry)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
