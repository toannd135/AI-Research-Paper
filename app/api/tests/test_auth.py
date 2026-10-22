"""Đăng ký/đăng nhập, phân quyền admin và cô lập dữ liệu theo người dùng (DB SQLite in-memory, JWT thật)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user, get_current_user_or_query_token
from app.api.models.paper import Paper
from app.api.models.user import ROLE_ADMIN, User
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # Test này cần xác thực thật, bỏ admin giả của conftest.
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_or_query_token, None)
    test_client = TestClient(app)
    test_client.session_factory = factory
    yield test_client
    app.dependency_overrides.clear()


def _register(client, email, password="matkhau-123"):
    return client.post("/auth/register", json={"email": email, "password": password, "full_name": email})


def _headers(client, email):
    token = _register(client, email).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_admin(client, email="admin@x.com", password="admin-pass-1"):
    with client.session_factory() as db:
        db.add(User(email=email, password_hash=hash_password(password), role=ROLE_ADMIN))
        db.commit()
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_register_login_and_me(client):
    response = _register(client, "A@Example.com")
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "user"

    login = client.post("/auth/login", json={"email": "a@example.com", "password": "matkhau-123"})
    assert login.status_code == 200
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert me.json()["email"] == "a@example.com"


def test_duplicate_email_and_wrong_password(client):
    _register(client, "a@example.com")
    assert _register(client, "a@example.com").status_code == 409
    bad = client.post("/auth/login", json={"email": "a@example.com", "password": "sai-mat-khau"})
    assert bad.status_code == 401


def test_weak_password_is_rejected(client):
    assert _register(client, "a@example.com", password="123").status_code == 422


def test_protected_routes_require_token(client):
    assert client.get("/papers").status_code == 401
    assert client.get("/research").status_code == 401
    assert client.get("/conversations").status_code == 401
    assert client.get("/papers", headers={"Authorization": "Bearer rac"}).status_code == 401
    assert client.get("/health").status_code == 200


def test_user_cannot_use_admin_endpoints(client):
    headers = _headers(client, "u@example.com")
    assert client.get("/auth/users", headers=headers).status_code == 403


def test_users_only_see_their_own_papers(client):
    a = _headers(client, "a@example.com")
    b = _headers(client, "b@example.com")
    admin = _make_admin(client)
    with client.session_factory() as db:
        owner = db.query(User).filter(User.email == "a@example.com").one()
        db.add(Paper(id="p1", filename="a.pdf", file_path="/tmp/a.pdf", status="done", user_id=owner.id))
        db.commit()

    assert [p["id"] for p in client.get("/papers", headers=a).json()["items"]] == ["p1"]
    assert client.get("/papers", headers=b).json()["items"] == []
    assert client.get("/papers/p1", headers=b).status_code == 404
    assert client.get("/papers/p1", headers=admin).status_code == 200


def test_admin_can_change_role_but_not_remove_last_admin(client):
    admin = _make_admin(client)
    _register(client, "u@example.com")
    users = client.get("/auth/users", headers=admin).json()
    target = next(u for u in users if u["email"] == "u@example.com")
    assert client.patch(f"/auth/users/{target['id']}", json={"role": "admin"}, headers=admin).status_code == 200
    only_admin = next(u for u in users if u["email"] == "admin@x.com")
    client.patch(f"/auth/users/{target['id']}", json={"role": "user"}, headers=admin)
    last = client.patch(f"/auth/users/{only_admin['id']}", json={"role": "user"}, headers=admin)
    assert last.status_code == 409


def test_disabled_user_cannot_log_in(client):
    admin = _make_admin(client)
    _register(client, "u@example.com")
    target = next(u for u in client.get("/auth/users", headers=admin).json() if u["email"] == "u@example.com")
    client.patch(f"/auth/users/{target['id']}", json={"is_active": False}, headers=admin)
    login = client.post("/auth/login", json={"email": "u@example.com", "password": "matkhau-123"})
    assert login.status_code == 403


def test_ensure_admin_uses_dev_default_only_in_local(monkeypatch):
    from app.api.routes import auth as auth_routes

    created: list[str] = []

    class FakeDb:
        def add(self, user):
            created.append(user.email)

        def commit(self):
            pass

    def fake_settings(env):
        return type("S", (), {"admin_email": None, "admin_password": None, "env": env})()

    monkeypatch.setattr(auth_routes, "_find_by_email", lambda db, email: None)
    monkeypatch.setattr(auth_routes, "get_settings", lambda: fake_settings("local"))
    auth_routes.ensure_admin(FakeDb())
    assert created == ["admin@gmail.com"]

    created.clear()
    monkeypatch.setattr(auth_routes, "get_settings", lambda: fake_settings("production"))
    auth_routes.ensure_admin(FakeDb())
    assert created == []
