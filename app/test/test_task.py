from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient


def _future_iso(days: int = 7) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _past_iso(days: int = 2) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@pytest.mark.asyncio
async def test_tasks_unauthorized(client: AsyncClient) -> None:
    response = await client.get("/tasks")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_task_lifecycle_and_status_rules(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    create_resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={
            "title": "Build backend API",
            "description": "Tasks and comments module",
            "priority": "High",
            "deadline": _future_iso(10),
            "status": "Backlog",
        },
    )
    assert create_resp.status_code == 201
    task = create_resp.json()
    task_id = task["id"]
    assert task["status"] == "Backlog"

    # 1. Assign user while task is still allowed to change assignee (Backlog)
    me_resp = await client.get("/users/me", headers=auth_headers)
    user_id = me_resp.json()["id"]

    assign_resp = await client.patch(
        f"/tasks/{task_id}",
        headers=auth_headers,
        json={"assignee_id": user_id},
    )
    assert assign_resp.status_code == 200
    assert assign_resp.json()["assignee_id"] == user_id

    # 2. Move to In Progress and verify backward transition to Backlog fails
    to_progress = await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": "In Progress"},
    )
    assert to_progress.status_code == 200

    back_to_backlog = await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": "Backlog"},
    )
    assert back_to_backlog.status_code == 400

    # 3. Cannot delete task while In Progress
    delete_in_progress = await client.delete(
        f"/tasks/{task_id}",
        headers=auth_headers,
    )
    assert delete_in_progress.status_code == 400

    # 4. Move to Review, verify changing assignee in Review is forbidden (400), then move to Done
    to_review = await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": "Review"},
    )
    assert to_review.status_code == 200

    change_assignee_in_review = await client.patch(
        f"/tasks/{task_id}",
        headers=auth_headers,
        json={"assignee_id": user_id + 999},
    )
    assert change_assignee_in_review.status_code == 400

    to_done = await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": "Done"},
    )
    assert to_done.status_code == 200
    assert to_done.json()["status"] == "Done"

    # 5. Cannot edit task in Done status, can delete after Done
    edit_done = await client.patch(
        f"/tasks/{task_id}",
        headers=auth_headers,
        json={"title": "Edited after Done"},
    )
    assert edit_done.status_code == 400

    delete_done = await client.delete(f"/tasks/{task_id}", headers=auth_headers)
    assert delete_done.status_code == 204


@pytest.mark.asyncio
async def test_cannot_move_to_done_without_assignee(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    create_resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={
            "title": "Unassigned task",
            "deadline": _future_iso(5),
            "status": "Backlog",
        },
    )
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]

    assert (
        await client.patch(
            f"/tasks/{task_id}/status",
            headers=auth_headers,
            json={"status": "In Progress"},
        )
    ).status_code == 200

    assert (
        await client.patch(
            f"/tasks/{task_id}/status",
            headers=auth_headers,
            json={"status": "Review"},
        )
    ).status_code == 200

    done_without_assignee = await client.patch(
        f"/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": "Done"},
    )
    assert done_without_assignee.status_code == 400


@pytest.mark.asyncio
async def test_deadline_validation_on_create(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={
            "title": "Past deadline task",
            "deadline": _past_iso(1),
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_active_tasks_limit(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    for i in range(10):
        resp = await client.post(
            "/tasks",
            headers=auth_headers,
            json={
                "title": f"Active task {i + 1}",
                "deadline": _future_iso(5),
            },
        )
        assert resp.status_code == 201

    overflow_resp = await client.post(
        "/tasks",
        headers=auth_headers,
        json={
            "title": "Active task 11",
            "deadline": _future_iso(5),
        },
    )
    assert overflow_resp.status_code == 400