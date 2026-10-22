"""Mặc định mọi test route chạy với một admin giả; test xác thực/phân quyền tự gỡ override này."""

from types import SimpleNamespace

import pytest

from app.api.deps import get_current_user, get_current_user_or_query_token
from app.main import app


@pytest.fixture(autouse=True)
def fake_admin():
    admin = SimpleNamespace(id="test-admin", email="admin@test", role="admin", is_active=True, full_name="Admin")
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_or_query_token] = lambda: admin
    yield admin
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_or_query_token, None)
