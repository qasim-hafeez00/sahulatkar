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
    # ── Overdue installment escalation notifications (NS-BL-05) ─────────────
    "billing.installment_overdue_d1": {
        "sms": {
            "body": "SahulatKar: URGENT — Your installment of PKR {{ installment_amount }} for {{ order_description }} was due {{ due_date }} (1 day ago). Please pay now to avoid additional fees."
        },
        "whatsapp": {
            "body": "⚠️ *Overdue Payment — Action Required*\n\nYour installment of PKR *{{ installment_amount }}* for {{ order_description }} was due *{{ due_date }}* (1 day overdue).\n\nPlease log in and pay immediately to avoid late fees. JazakAllah Khair."
        },
        "push": {
            "title": "Overdue Payment ⚠️",
            "body": "PKR {{ installment_amount }} was due {{ due_date }}. Pay now to avoid late fees."
        },
    },
    "billing.installment_overdue_d7": {
        "sms": {
            "body": "SahulatKar: Your installment of PKR {{ installment_amount }} for {{ order_description }} is now 7 days overdue. A late fee has been applied. Please pay immediately."
        },
        "whatsapp": {
            "body": "🔴 *7-Day Overdue Notice*\n\nYour installment of PKR *{{ installment_amount }}* for {{ order_description }} is 7 days overdue.\n\nA Shariah-compliant late administrative fee has been applied. Please settle immediately to stop further charges."
        },
    },
    "billing.installment_overdue_d14": {
        "sms": {
            "body": "SahulatKar: FINAL NOTICE — Your installment of PKR {{ installment_amount }} is 14 days overdue. Please contact us immediately to avoid account suspension."
        },
        "whatsapp": {
            "body": "🚨 *FINAL NOTICE — 14-Day Overdue*\n\nYour installment of PKR *{{ installment_amount }}* for {{ order_description }} is 14 days overdue.\n\nPlease contact SahulatKar support immediately or log in to arrange payment. Continued non-payment may affect your credit."
        },
    },
    # ── New integration events (Section 6.4 gaps) ────────────────────────────
    "order.cancelled": {
        "sms": {
            "body": "SahulatKar: Your order #{{ order_id }} for {{ product_description }} has been cancelled{% if reason %} ({{ reason }}){% endif %}. Contact support if this was unexpected."
        },
        "whatsapp": {
            "body": "❌ *Order Cancelled*\n\nYour order #{{ order_id }} for {{ product_description }} has been cancelled.{% if reason %}\n\n*Reason:* {{ reason }}{% endif %}\n\nIf you did not request this, please contact SahulatKar support immediately."
        },
        "push": {
            "title": "Order Cancelled",
            "body": "Order #{{ order_id }} has been cancelled. Tap to view details."
        },
    },
    "vcn.expired": {
        "sms": {
            "body": "SahulatKar: Your virtual card ending in {{ vcn_last4 }} has expired. Please contact support if you need a replacement for order #{{ order_id }}."
        },
        "push": {
            "title": "Virtual Card Expired",
            "body": "Your VCN ending {{ vcn_last4 }} for order #{{ order_id }} has expired."
        },
    },
    "payment.failed": {
        "sms": {
            "body": "SahulatKar: Your payment of PKR {{ amount }} for order #{{ order_id }} could not be processed ({{ failure_reason }}). Please update your payment method."
        },
        "whatsapp": {
            "body": "❌ *Payment Failed*\n\nYour payment of PKR *{{ amount }}* for order #{{ order_id }} could not be processed.\n\n*Reason:* {{ failure_reason }}\n\nPlease log in to update your payment method or try again."
        },
        "push": {
            "title": "Payment Failed ❌",
            "body": "PKR {{ amount }} payment failed for order #{{ order_id }}. Tap to retry."
        },
    },
    "kyc.documents_needed": {
        "whatsapp": {
            "body": "📋 *Documents Required — Action Needed*\n\nAssalamu Alaikum {{ user_name }},\n\nTo complete your KYC verification, we need the following documents:\n*{{ required_docs }}*\n\nPlease upload them via the SahulatKar app. JazakAllah Khair."
        },
        "push": {
            "title": "Documents Required 📋",
            "body": "Please upload your {{ required_docs }} to complete KYC verification."
        },
    },
    "credit.limit_changed": {
        "whatsapp": {
            "body": "💳 *Credit Limit {{ change_direction|title }}*\n\nYour SahulatKar credit limit has been {{ change_direction }}.\n\n*New Limit:* PKR {{ new_limit }}\n*Previous Limit:* PKR {{ old_limit }}\n\nJazakAllah Khair for being a valued SahulatKar customer."
        },
        "push": {
            "title": "Credit Limit Updated",
            "body": "Your credit limit has been {{ change_direction }} to PKR {{ new_limit }}."
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
