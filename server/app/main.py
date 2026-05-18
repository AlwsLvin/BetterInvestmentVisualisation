from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, market, portfolio, search, settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="BetterInvestDecision API",
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_prefix = "/api"
    app.include_router(health.router, prefix=api_prefix, tags=["meta"])
    app.include_router(market.router, prefix=api_prefix, tags=["market"])
    app.include_router(portfolio.router, prefix=api_prefix, tags=["portfolio"])
    app.include_router(search.router, prefix=api_prefix, tags=["search"])
    app.include_router(settings.router, prefix=api_prefix, tags=["settings"])
    return app


app = create_app()
