from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient


def _future_iso(days: int = 7) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


@pytest.mark.asyncio
async def test_comments_unauthorized(client: AsyncClient) -> None:
    response = await client.get("/tasks/1/comments")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_comments_create_and_list(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    task_resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={
            "title": "Task with comments",
            "deadline": _future_iso(5),
        },
    )
    assert task_resp.status_code == 201
    task_id = task_resp.json()["id"]

    # Create comment
    comment_resp = await client.post(
        f"/tasks/{task_id}/comments",
        headers=auth_headers,
        json={"content": "Looks good so far"},
    )
    assert comment_resp.status_code == 201
    assert comment_resp.json()["content"] == "Looks good so far"
    assert comment_resp.json()["task_id"] == task_id

    # List comments
    list_resp = await client.get(
        f"/tasks/{task_id}/comments",
        headers=auth_headers,
    )
    assert list_resp.status_code == 200
    comments = list_resp.json()
    assert len(comments) == 1
    assert comments[0]["content"] == "Looks good so far"


@pytest.mark.asyncio
async def test_comments_missing_task_returns_404(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    create_resp = await client.post(
        "/tasks/999999/comments",
        headers=auth_headers,
        json={"content": "Comment for missing task"},
    )
    assert create_resp.status_code == 404

    list_resp = await client.get(
        "/tasks/999999/comments",
        headers=auth_headers,
    )
    assert list_resp.status_code == 404