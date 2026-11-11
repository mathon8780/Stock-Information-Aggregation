from typing import Literal

from fastapi import APIRouter, Path, Query

from app.services.market_board_service import market_boards

router = APIRouter(prefix="/api/v1/market", tags=["market boards"])


@router.get("/boards")
def get_boards(kind: Literal["industry", "concept"] = "industry"):
    return market_boards.boards(kind)


@router.get("/boards/{code}/constituents")
def get_constituents(code: str = Path(pattern=r"^BK\d+$"), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), sort_order: Literal["asc", "desc"] = "desc"):
    return market_boards.constituents(code, page, page_size, sort_order)
