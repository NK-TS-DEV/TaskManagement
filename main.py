from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers import api_router
from app.core.background import background_tasks_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    background_tasks_manager.start()
    try:
        yield
    finally:
        await background_tasks_manager.stop()


app = FastAPI(title="tasks Management API", lifespan=lifespan)

app.include_router(api_router)
