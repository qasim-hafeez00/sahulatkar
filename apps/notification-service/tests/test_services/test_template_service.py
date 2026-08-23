from src.services.template_service import TemplateService

def test_sms_template_max_160_chars():
    ts = TemplateService()
    title, body = ts.render(
        "kyc.approved",
        "sms",
        {"credit_limit": "50000"}
    )
    assert len(body) <= 160
    assert "50000" in body

def test_push_title_max_50_chars():
    ts = TemplateService()
    title, body = ts.render("kyc.approved", "push", {"credit_limit": "50000"})
    assert len(title) <= 50

def test_push_body_max_100_chars():
    ts = TemplateService()
    title, body = ts.render("kyc.approved", "push", {"credit_limit": "50000"})
    assert len(body) <= 100

def test_late_fee_template_contains_shariah_elements():
    ts = TemplateService()
    vars = {
        "fee_amount": "50",
        "days_overdue": "2",
        "order_id": "123",
        "charity_org": "Edhi Foundation",
        "fee_disclosure": "actual costs only, not riba"
    }
    
    # SMS
    t, b = ts.render("billing.late_fee_applied", "sms", vars)
    assert "50" in b
    assert "not riba" in b or "actual costs" in b
    assert "Edhi Foundation" in b
    
    # WhatsApp
    t, b = ts.render("billing.late_fee_applied", "whatsapp", vars)
    assert "50" in b
    assert "actual costs only, not riba" in b
    assert "Edhi Foundation" in b

    # Email
    t, b = ts.render("billing.late_fee_applied", "email", vars)
    assert "50" in b
    assert "actual costs only, not riba" in b
    assert "Edhi Foundation" in b

def test_contract_signed_email_contains_murabaha_terms():
    ts = TemplateService()
    vars = {
        "order_id": "123",
        "cost_price": "1000",
        "profit_amount": "100",
        "total_amount": "1100",
        "down_payment": "200",
        "installment_count": "5"
    }
    t, b = ts.render("contract.signed", "email", vars)
    assert "1000" in b
    assert "100" in b
    assert "1100" in b
    assert "200" in b
    assert "5" in b

def test_unknown_event_returns_generic_fallback():
    ts = TemplateService()
    title, body = ts.render("unknown.event", "sms", {})
    assert title == "SahulatKar Notification"
    assert "unknown event" in body

def test_missing_template_var_returns_safe_fallback():
    ts = TemplateService()
    title, body = ts.render("kyc.approved", "sms", {})
    assert "credit_limit" in body  # It should return the unrendered template string if variable is missing
