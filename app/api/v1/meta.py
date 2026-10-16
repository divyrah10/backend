import hmac

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.meta import catalog_csv

router = APIRouter()


@router.get("/catalog.csv")
def catalog_feed(token: str = Query(default=""), db: Session = Depends(get_db)):
    """Product feed for a Meta catalog (Commerce Manager > Data sources > Data feed > Scheduled feed)."""
    if settings.META_CATALOG_FEED_TOKEN and not hmac.compare_digest(token, settings.META_CATALOG_FEED_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid feed token")
    return Response(
        content=catalog_csv(db),
        media_type="text/csv; charset=utf-8",
        headers={"Cache-Control": "public, max-age=900"},
    )
