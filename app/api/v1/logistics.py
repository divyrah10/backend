import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.shiprocket import apply_tracking_update

logger = logging.getLogger(__name__)

router = APIRouter()


# Shiprocket rejects webhook URLs containing "shiprocket", "kartrocket", "sr" or "kr",
# hence the neutral /logistics/tracking path.
@router.post("/tracking")
async def tracking_webhook(
    request: Request,
    x_api_key: str = Header(default=""),
    db: Session = Depends(get_db),
):
    if not settings.SHIPROCKET_WEBHOOK_TOKEN:
        raise HTTPException(status_code=503, detail="Tracking webhook is not configured")
    if not hmac.compare_digest(x_api_key, settings.SHIPROCKET_WEBHOOK_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid webhook payload")

    shipment = apply_tracking_update(db, payload if isinstance(payload, dict) else {})
    if shipment:
        db.commit()
    else:
        # Acknowledge anyway so Shiprocket doesn't retry updates for orders we don't hold.
        logger.info("Tracking update for unknown shipment (awb=%s)", payload.get("awb"))
    return {"status": "ok"}
