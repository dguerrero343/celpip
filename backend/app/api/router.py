from fastapi import APIRouter

from app.api import admin, auth, demo, health, usage, writing

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(writing.router)
api_router.include_router(usage.router)
api_router.include_router(demo.router)
api_router.include_router(admin.router)
