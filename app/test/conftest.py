import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.database import Base, get_async_session  # noqa: E402
from app.modules.comments import models as _comments_models  # noqa: F401, E402
from app.modules.tasks import models as _tasks_models  # noqa: F401, E402
from app.modules.users import models as _users_models  # noqa: F401, E402
from main import app  # noqa: E402


def _build_test_database_url(base_url: str) -> str:
    explicit_test_url = getattr(settings, "TEST_DATABASE_URL", None)
    if explicit_test_url:
        return str(explicit_test_url)

    parsed = urlparse(str(base_url))
    db_name = parsed.path.lstrip("/")
    test_db_name = db_name if db_name.endswith("_test") else f"{db_name}_test"
    return urlunparse(parsed._replace(path=f"/{test_db_name}"))


TEST_DATABASE_URL = _build_test_database_url(str(settings.DATABASE_URL))


@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def prepare_database(db_engine: AsyncEngine) -> AsyncGenerator[None, None]:
    yield
    async with db_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def client(db_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async def override_get_async_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.close()

    app.dependency_overrides[get_async_session] = override_get_async_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as async_client:
            yield async_client
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    email = f"user_{uuid4().hex[:8]}@example.com"
    password = "StrongPassword123!"

    reg_resp = await client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    assert reg_resp.status_code in (200, 201)

    login_resp = await client.post(
        "/auth/login",
        data={"username": email, "password": password},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}