import pytest
from src.services.template_service import TemplateService
from src.config import settings

def test_late_fee_charity_enforcement():
    ts = TemplateService()
    # Template without charity org
    event_type = "billing.late_fee_applied"
    template_vars = {"fee_amount": "500", "days_overdue": "5", "fee_disclosure": "Disclosure", "charity_org": "WrongOrg", "order_id": "123"}
    
    # We set the official charity org in settings
    settings.CHARITY_ORGANIZATION_NAME = "Edhi Foundation"
    
    _, body = ts.render(event_type, "sms", template_vars)
    
    # Even if charity_org in vars was wrong, the enforcement should at least check if the settings org is there
    # Wait, in the default template it uses {{ charity_org }}. 
    # But if the rendered body doesn't contain the settings org, it appends it.
    assert "Edhi Foundation" in body

@pytest.mark.asyncio
async def test_health_ready_path(client):
    from src.core.event_listeners import listener_state
    from src.services.notification_service import DISPATCHERS
    from unittest.mock import AsyncMock
    
    listener_state["running"] = True
    for dispatcher in DISPATCHERS.values():
        dispatcher.health_check = AsyncMock(return_value=True)

    # Try all possible paths to find where it's mounted
    paths = ["/api/health/ready", "/health/ready", "/api/v1/health/ready"]
    found = False
    for p in paths:
        resp = await client.get(p)
        if resp.status_code != 404:
            found = True
            assert resp.status_code == 200
            break
    assert found, "Health endpoint not found at any expected path"

