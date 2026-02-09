"""Tests for the API routes."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from knowitall.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_check(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "knowItAll"
        assert "version" in data
