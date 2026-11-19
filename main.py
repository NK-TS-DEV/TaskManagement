from fastapi import FastAPI

from app.api.routers import api_router

app = FastAPI(title="tasks Management API")

app.include_router(api_router)


