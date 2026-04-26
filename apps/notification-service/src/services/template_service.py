from jinja2 import Environment, StrictUndefined, TemplateError

from src.config import settings

jinja_env = Environment(undefined=StrictUndefined, autoescape=False)

DEFAULT_TEMPLATES: dict[str, dict[str, dict[str, str]]] = {
    "kyc.approved": {
        "sms": {
            "body": "SahulatKar: Mubarak! Your account is approved. Credit limit: PKR {{ credit_limit }}. Start shopping now!"
        },
        "whatsapp": {
            "body": "🎉 *Mubarak {{ user_name }}!*\n\nYour SahulatKar account is now approved.\n\n💳 *Credit Limit:* PKR {{ credit_limit }}\n\nYou can now start BNPL shopping. JazakAllah Khair."
        },
        "push": {
            "title": "Account Approved! 🎉",
            "body": "Your SahulatKar account is approved. Credit limit: PKR {{ credit_limit }}"
        },
    },
    "kyc.rejected": {
        "sms": {
            "body": "SahulatKar: Unfortunately your KYC could not be approved at this time ({{ rejection_reason }}). Please contact support."
        },
        "whatsapp": {
            "body": "Assalamu Alaikum {{ user_name }},\n\nWe were unable to approve your account at this time.\n\n📋 *Reason:* {{ rejection_reason }}\n\nPlease re-apply after addressing the issue or contact our support team."
        },
        "push": {
            "title": "KYC Update",
            "body": "Your application could not be approved. Tap to view details."
        },
    },
    "payment.down_payment_confirmed": {
        "sms": {
            "body": "SahulatKar: PKR {{ amount }} payment confirmed for order #{{ order_id }}. Your purchase is being processed. JazakAllah Khair."
        },
        "whatsapp": {
            "body": "✅ *Payment Confirmed!*\n\nPKR *{{ amount }}* received for {{ product_description }} (Order #{{ order_id }}).\n\nYour agent is now completing your purchase. We'll update you shortly. JazakAllah Khair."
        },
        "push": {
            "title": "Payment Confirmed ✅",
            "body": "PKR {{ amount }} received. Your order is being processed."
        },
        "email": {
            "subject": "Payment Confirmation — SahulatKar Order #{{ order_id }}",
            "body": "Assalamu Alaikum,\n\nThis confirms receipt of your down payment of PKR {{ amount }} for Order #{{ order_id }} ({{ product_description }}).\n\nYour purchase agent is now completing your order. You will receive another notification once the order is placed.\n\nJazakAllah Khair,\nSahulatKar Team"
        },
    },
    "contract.signed": {
        "whatsapp": {
            "body": "📝 *Murabaha Contract Signed*\n\nYour Shariah-compliant financing is now active.\n\n💰 Cost Price: PKR {{ cost_price }}\n📈 Profit: PKR {{ profit_amount }}\n💳 Total: PKR {{ total_amount }}\n📆 {{ installment_count }} bi-weekly installments\n\nJazakAllah Khair."
        },
        "push": {
            "title": "Contract Signed ✅",
            "body": "Your Murabaha contract is active. Order #{{ order_id }} is now financed."
        },
        "email": {
            "subject": "Your Murabaha Financing Contract — SahulatKar Order #{{ order_id }}",
            "body": "Assalamu Alaikum,\n\nYour Murabaha contract for Order #{{ order_id }} has been signed and is now active.\n\nFinancing Summary:\n- Cost Price (Thaman): PKR {{ cost_price }}\n- SahulatKar Profit (disclosed per Shariah): PKR {{ profit_amount }}\n- Total You Pay: PKR {{ total_amount }}\n- Down Payment Made: PKR {{ down_payment }}\n- Remaining: {{ installment_count }} bi-weekly installments\n\nThis contract complies with Shariah principles as reviewed by our Shariah Board. A copy of your signed contract is attached.\n\nJazakAllah Khair,\nSahulatKar Shariah-Compliant Finance"
        },
    },
    "billing.late_fee_applied": {
        "sms": {
            "body": "SahulatKar: A fee of PKR {{ fee_amount }} has been applied ({{ days_overdue }} days overdue). This covers actual costs only, not riba. 100% goes to {{ charity_org }}. Please pay now."
        },
        "whatsapp": {
            "body": "⚠️ *Late Fee Applied — Order #{{ order_id }}*\n\n*Amount:* PKR {{ fee_amount }}\n*Days Overdue:* {{ days_overdue }}\n\n📋 *Important Shariah Disclosure:*\n{{ fee_disclosure }}\n\n100% of this amount is donated to *{{ charity_org }}*.\n\nPlease log in to pay your overdue installment."
        },
        "push": {
            "title": "Late Fee Applied — Action Required",
            "body": "PKR {{ fee_amount }} applied to Order #{{ order_id }}. This is donated 100% to {{ charity_org }}. Tap to pay."
        },
        "email": {
            "subject": "Late Fee Notice — Shariah Disclosure — Order #{{ order_id }}",
            "body": "Assalamu Alaikum,\n\nA late administrative fee of PKR {{ fee_amount }} has been applied to your account for Order #{{ order_id }} ({{ days_overdue }} days overdue).\n\n--- SHARIAH COMPLIANCE DISCLOSURE ---\n{{ fee_disclosure }}\n\n100% of this fee amount (PKR {{ fee_amount }}) will be donated to {{ charity_org }}.\n\nThis is in accordance with SahulatKar's Shariah-compliant finance structure approved by our Shariah Supervisory Board.\n--- END DISCLOSURE ---\n\nPlease log in to your account immediately to settle your outstanding installment.\n\nJazakAllah Khair,\nSahulatKar Compliance Team"
        },
    },
    "billing.installment_due_d1": {
        "sms": {
            "body": "SahulatKar: Your installment of PKR {{ installment_amount }} for {{ order_description }} is due TOMORROW ({{ due_date }}). Please ensure funds are available."
        },
        "whatsapp": {
            "body": "📅 *Installment Reminder*\n\nYour payment of PKR *{{ installment_amount }}* for {{ order_description }} is due *tomorrow, {{ due_date }}*.\n\nPlease ensure your JazzCash / bank account has sufficient balance. JazakAllah Khair."
        },
        "push": {
            "title": "Payment Due Tomorrow 📅",
            "body": "PKR {{ installment_amount }} for {{ order_description }} is due {{ due_date }}."
        },
    },
    "billing.installment_due_d3": {
        "whatsapp": {
            "body": "📅 *Upcoming Installment Reminder*\n\nYour payment of PKR *{{ installment_amount }}* for {{ order_description }} is due in *3 days ({{ due_date }})*.\n\nJazakAllah Khair."
        },
        "push": {
            "title": "Payment Due in 3 Days",
            "body": "PKR {{ installment_amount }} due {{ due_date }} for {{ order_description }}."
        },
    },
    "billing.installment_paid": {
        "whatsapp": {
            "body": "✅ *Payment Received!*\n\nPKR *{{ installment_amount }}* received (Installment {{ installment_number }}/{{ total_installments }}).\n\nRemaining balance: PKR {{ remaining_amount }}. JazakAllah Khair."
        },
        "push": {
            "title": "Installment Paid ✅",
            "body": "PKR {{ installment_amount }} received. {{ installment_number }}/{{ total_installments }} paid."
        },
    },
    "delivery.confirmed": {
        "sms": {
            "body": "SahulatKar: Your order #{{ order_id }} has been delivered! Enjoy your {{ product_description }}. JazakAllah Khair."
        },
        "whatsapp": {
            "body": "📦 *Order Delivered!*\n\n{{ product_description }} (Order #{{ order_id }}) has been delivered.\n\n🚚 Courier: {{ courier }}\n📋 Tracking: {{ tracking_number }}\n\nPlease inspect your package. Report any issues via the app. JazakAllah Khair."
        },
        "push": {
            "title": "Order Delivered! 📦",
            "body": "Your {{ product_description }} has arrived. Tap to confirm receipt."
        },
    },
    "billing.loan_fully_repaid": {
        "whatsapp": {
            "body": "🎉 *Congratulations!*\n\nYou have fully repaid your financing for {{ product_description }}!\n\n💰 *Total Paid:* PKR {{ total_paid }}\n\nYour account is now clear. We look forward to serving you again. JazakAllah Khair wa Barakallah Feek."
        },
        "push": {
            "title": "Loan Fully Repaid! 🎉",
            "body": "Mubarak! Your {{ product_description }} is fully paid off."
        },
        "email": {
            "subject": "Financing Complete — Congratulations! — SahulatKar",
            "body": "Assalamu Alaikum,\n\nAlhamdulillah! You have successfully completed your Murabaha financing.\n\nTotal Amount Paid: PKR {{ total_paid }}\nProduct: {{ product_description }}\n\nJazakAllah Khair for trusting SahulatKar with your financing needs. We look forward to serving you again.\n\nWas-Salamu Alaikum,\nSahulatKar Team"
        },
    },
}


class TemplateService:
    def render(self, event_type: str, channel: str, template_vars: dict) -> tuple[str, str]:
        """
        Render notification content for a specific event + channel.
        Returns (title, body).
        """
        event_templates = DEFAULT_TEMPLATES.get(event_type, {})
        channel_template = event_templates.get(channel, {})

        if not channel_template:
            return ("SahulatKar Notification", f"Update regarding your {event_type.replace('.', ' ')}.")

        title = channel_template.get("title", "SahulatKar")
        body_template = channel_template.get("body", "")
        subject = channel_template.get("subject", title)

        try:
            rendered_title = jinja_env.from_string(subject).render(**template_vars)
            rendered_body = jinja_env.from_string(body_template).render(**template_vars)
        except TemplateError:
            # Fallback
            rendered_title = title
            rendered_body = body_template

        # Limits
        if channel == "sms":
            rendered_body = rendered_body[:160]
        elif channel == "push":
            rendered_title = rendered_title[:50]
            rendered_body = rendered_body[:100]
        elif channel == "whatsapp":
            rendered_body = rendered_body[:1024]
        elif channel == "email":
            unsub_link = f"{settings.CUSTOMER_WEB_URL}/notifications/unsubscribe"
            rendered_body += f"\n\n---\nYou are receiving this because you signed up for SahulatKar. To unsubscribe from all non-essential notifications, visit: {unsub_link}"

        # ── Shariah Compliance Enforcement ───────────────────────────────────
        # Ensure mandatory charity disclosure for all late fee/penalty events
        if "late_fee" in event_type or "penalty" in event_type:
            charity = settings.CHARITY_ORGANIZATION_NAME
            if charity not in rendered_body:
                # Force append if missing — mandatory Shariah requirement for SahulatKar
                rendered_body += f"\nNote: 100% of this amount is donated to {charity}."
        
        # Ensure riba-free disclosure for installment notices if missing
        if "billing.installment" in event_type and "due" in event_type:
            if "SahulatKar" not in rendered_body:
                rendered_body = f"SahulatKar: {rendered_body}"

        return (rendered_title, rendered_body)
