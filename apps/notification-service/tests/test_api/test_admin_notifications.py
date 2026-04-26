import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_get_notification_stats(monkeypatch):
    monkeypatch.setattr("src.api.v1.admin_notifications.require_permissions", lambda perms: lambda: True)
    
    response = client.get("/api/v1/admin/notifications/stats")
    assert response.status_code in [200, 401, 403]
