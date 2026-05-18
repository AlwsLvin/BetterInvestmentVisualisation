from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas import SearchResponse, SearchResult

router = APIRouter()

_SEARCH_TIMEOUT = 5
_MAX_LIMIT = 50


def _yfinance_search(q: str, limit: int) -> list[SearchResult]:
    """Hit Yahoo Finance's lookup via yfinance.Search.

    Wrapped so tests can monkey-patch this single function instead of
    pulling in the full yfinance machinery. Falls back to an empty list
    on any network/parse error rather than failing the whole request.
    """
    try:
        import yfinance as yf
        s = yf.Search(
            q,
            max_results=limit,
            news_count=0,
            lists_count=0,
            include_research=False,
            include_cultural_assets=False,
            enable_fuzzy_query=True,
            recommended=limit,
            timeout=_SEARCH_TIMEOUT,
        )
        quotes = s.quotes or []
    except Exception:
        return []

    out: list[SearchResult] = []
    for item in quotes[:limit]:
        if item.get("isYahooFinance") is False:
            continue
        symbol = (item.get("symbol") or "").strip()
        if not symbol:
            continue
        out.append(SearchResult(
            symbol=symbol,
            name=(item.get("longname") or item.get("shortname") or "").strip(),
            exchange=(item.get("exchDisp") or item.get("exchange") or "").strip(),
            type=(item.get("typeDisp") or item.get("quoteType") or "").strip(),
        ))
    return out


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(min_length=1, max_length=64),
    limit: int = Query(default=10, ge=1, le=_MAX_LIMIT),
) -> SearchResponse:
    query = q.strip()
    return SearchResponse(query=query, results=_yfinance_search(query, limit))
