from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, UTC

from app.database.models import PermissionRequest
from app.database.session import get_db
from app.security.permissions import permission_manager
from app.api.websocket import ws_manager
from app.schemas.permission import PermissionResponse, PermissionListResponse

router = APIRouter()


@router.get("", response_model=list[PermissionResponse])
async def list_permissions(
    status: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    query = select(PermissionRequest).order_by(PermissionRequest.created_at.desc()).limit(limit)
    if status:
        query = query.where(PermissionRequest.status == status)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/pending", response_model=list[PermissionResponse])
async def list_pending_permissions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PermissionRequest)
        .where(PermissionRequest.status == "pending")
        .order_by(PermissionRequest.created_at.desc())
    )
    return result.scalars().all()


@router.post("/{request_id}/approve")
async def approve_permission(
    request_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending permission request.

    The backend validates the request exists and is pending before resolving.
    The frontend cannot bypass this validation.
    """
    result = await db.execute(
        select(PermissionRequest).where(PermissionRequest.id == request_id)
    )
    perm = result.scalar_one_or_none()

    if not perm:
        raise HTTPException(status_code=404, detail="Permission request not found")
    if perm.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request is already {perm.status}")

    # Resolve in the permission manager (unblocks the agent)
    resolved = permission_manager.resolve(request_id, approved=True)

    if not resolved:
        # Request may have timed out
        perm.status = "expired"
        perm.resolved_at = datetime.now(UTC)
        await db.commit()
        raise HTTPException(status_code=410, detail="Permission request has expired")

    # DB update happens inside the agent's _request_permission method
    # but we also update here as a safety measure
    perm.status = "approved"
    perm.resolved_at = datetime.now(UTC)
    await db.commit()

    # Notify via WebSocket
    await ws_manager.broadcast_to_conversation(
        perm.conversation_id,
        {"type": "permission_resolved", "id": request_id, "approved": True},
    )

    return {"id": request_id, "status": "approved"}


@router.post("/{request_id}/deny")
async def deny_permission(
    request_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Deny a pending permission request."""
    result = await db.execute(
        select(PermissionRequest).where(PermissionRequest.id == request_id)
    )
    perm = result.scalar_one_or_none()

    if not perm:
        raise HTTPException(status_code=404, detail="Permission request not found")
    if perm.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request is already {perm.status}")

    resolved = permission_manager.resolve(request_id, approved=False)

    perm.status = "denied"
    perm.resolved_at = datetime.now(UTC)
    await db.commit()

    await ws_manager.broadcast_to_conversation(
        perm.conversation_id,
        {"type": "permission_resolved", "id": request_id, "approved": False},
    )

    return {"id": request_id, "status": "denied"}
