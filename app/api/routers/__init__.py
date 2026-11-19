from fastapi import APIRouter

from app.api.routers import users,tasks,comments

api_router = APIRouter()
api_router.include_router(users.router)
api_router.include_router(tasks.router)
api_router.include_router(comments.router)