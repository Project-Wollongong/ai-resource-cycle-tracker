from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...schemas import TodayBoard
from ...services.today_service import build_today
from ..deps import get_db

router = APIRouter(prefix="/today", tags=["today"])


@router.get("", response_model=TodayBoard)
def today_board(db: Session = Depends(get_db)):
    """Stocks with something to report today, and the tickers that stayed quiet.

    Read-only aggregation over existing scores, signals, announcements and P04
    features — it computes nothing new, so it cannot disagree with the pages
    that show those records individually.
    """
    return build_today(db)
