"""Mocked tests for Supabase token verification; these do not create real accounts."""

import io
import json
from urllib.error import HTTPError

import pytest
from fastapi import HTTPException

from backend import course_store, supabase_auth


class FakeAuthResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({"id": "verified-user-id", "email": "student@example.test"}).encode()


def test_valid_token_uses_verified_supabase_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(course_store, "DATABASE_PATH", tmp_path / "users.sqlite3")
    course_store.initialize_database()
    monkeypatch.setenv("SUPABASE_URL", "https://project.example.test")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-key-for-test")
    monkeypatch.setattr(supabase_auth, "urlopen", lambda request, timeout: FakeAuthResponse())

    result = supabase_auth.get_current_user("Bearer test-token")

    assert result["id"] == "verified-user-id"
    with course_store.connect() as database:
        row = database.execute("SELECT user_id FROM users").fetchone()
    assert row["user_id"] == "verified-user-id"


def test_invalid_token_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project.example.test")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-key-for-test")
    def reject(_request, timeout):
        raise HTTPError("https://project.example.test/auth/v1/user", 401, "invalid", {}, io.BytesIO())
    monkeypatch.setattr(supabase_auth, "urlopen", reject)

    with pytest.raises(HTTPException) as error:
        supabase_auth.get_current_user("Bearer invalid-token")
    assert error.value.status_code == 401


def test_missing_auth_configuration_is_reported(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)

    with pytest.raises(HTTPException) as error:
        supabase_auth.get_current_user("Bearer token")
    assert error.value.status_code == 503
