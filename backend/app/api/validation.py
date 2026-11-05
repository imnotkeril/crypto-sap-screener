"""Shared request validation helpers."""
import re
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import PairsScreeningResult
from app.modules.screener.live_screener import get_live_screener

_ASSET_RE = re.compile(r"^[A-Z0-9]{1,20}$")


def ensure_pair_exists(db: Optional[Session], pair_id: int, asset_a: str, asset_b: str) -> None:
    """Raise 422/404 unless pair_id is a known screened pair with these assets."""
    for asset in (asset_a, asset_b):
        if not _ASSET_RE.match(asset or ""):
            raise HTTPException(status_code=422, detail="Invalid asset symbol")
    wanted = {asset_a, asset_b}
    for r in get_live_screener().get_results():
        if r.get("id") == pair_id:
            if {r.get("asset_a"), r.get("asset_b")} != wanted:
                raise HTTPException(status_code=422, detail="Assets do not match pair_id")
            return
    if db is not None:
        row = db.query(PairsScreeningResult).filter(PairsScreeningResult.id == pair_id).first()
        if row is not None:
            if {row.asset_a, row.asset_b} != wanted:
                raise HTTPException(status_code=422, detail="Assets do not match pair_id")
            return
    raise HTTPException(status_code=404, detail="Pair not found")
