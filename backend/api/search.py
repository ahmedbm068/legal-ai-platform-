from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.core.deps import get_db, get_current_user
from backend.core.permissions import is_admin
from backend.models.user import User
from backend.services.lexical_search_service import lexical_search_documents
from backend.api.intelligence_schema import RetrievalSearchResponse as SearchResponse


router = APIRouter(prefix="/search", tags=["Search"])


@router.get("/documents", response_model=SearchResponse)
def search_documents(
    q: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    tenant_scope = None if is_admin(current_user) else current_user.tenant_id
    results = lexical_search_documents(db, tenant_scope, q)

    return {
        "query": q,
        "results": results
    }