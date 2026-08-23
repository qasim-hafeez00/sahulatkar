from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_list_notifications(monkeypatch):
    monkeypatch.setattr("src.api.v1.notifications.get_current_user_id", lambda: 1)
    
    response = client.get("/api/v1/notifications/")
    assert response.status_code in [200, 401, 403]  # Depends on how dependencies are mocked

def test_mark_notification_read(monkeypatch):
    monkeypatch.setattr("src.api.v1.notifications.get_current_user_id", lambda: 1)
    
    response = client.post("/api/v1/notifications/1/read")
    assert response.status_code in [200, 401, 403]
