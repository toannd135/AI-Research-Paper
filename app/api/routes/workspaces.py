"""POST /workspaces, GET /workspaces — phiên/đề tài nghiên cứu của người dùng."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import can_access, get_current_user
from app.api.models.user import ROLE_ADMIN, User
from app.api.models.workspace import Workspace
from app.core.database import get_db
from app.core.schemas import WorkspaceCreate, WorkspaceResponse, WorkspaceUpdate

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def get_owned_workspace_id(db: Session, user: User, workspace_id: str | None) -> str | None:
    """Trả về workspace_id nếu user được dùng; 404 nếu không tồn tại hoặc của người khác; None nếu không chỉ định."""
    if not workspace_id:
        return None
    ws = db.get(Workspace, workspace_id)
    if ws is None or not can_access(user, ws.user_id):
        raise HTTPException(status_code=404, detail="Workspace không tồn tại")
    return ws.id


@router.post("", response_model=WorkspaceResponse, status_code=201)
def create_workspace(
    payload: WorkspaceCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Workspace:
    ws = Workspace(user_id=user.id, name=payload.name.strip(), domain=payload.domain)
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
def update_workspace(
    workspace_id: str, payload: WorkspaceUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Workspace:
    """Đổi chế độ của kho; áp cho các lượt nghiên cứu bắt đầu SAU khi đổi (task đang chạy giữ chế độ đã đọc lúc bắt đầu)."""
    ws = db.get(Workspace, get_owned_workspace_id(db, user, workspace_id))
    ws.domain = payload.domain
    db.commit()
    db.refresh(ws)
    return ws


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[Workspace]:
    stmt = select(Workspace).order_by(Workspace.created_at.desc())
    if user.role != ROLE_ADMIN:
        stmt = stmt.where(Workspace.user_id == user.id)
    return list(db.scalars(stmt).all())
