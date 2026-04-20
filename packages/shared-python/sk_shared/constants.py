# packages/shared-python/sk_shared/constants.py

class OrderState:
    URL_SUBMITTED = "url_submitted"
    URL_RECEIVED = "url_received"
    EXTRACTING = "extracting"
    EXTRACTION_FAILED = "extraction_failed"
    OFFER_PRESENTED = "offer_presented"
    CONTRACTS_PENDING = "contracts_pending"
    CONTRACTS_SIGNED = "contracts_signed"
    DOWN_PAYMENT_PENDING = "down_payment_pending"
    DOWN_PAYMENT_RECEIVED = "down_payment_received"
    VCN_ISSUED = "vcn_issued"
    PURCHASING = "purchasing"
    PURCHASE_FAILED = "purchase_failed"
    PURCHASE_CONFIRMED = "purchase_confirmed"
    DELIVERY_PENDING = "delivery_pending"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    RETURNED = "returned"
    DISPUTED = "disputed"

class RedisNS:
    AUTH_OTP = "sk:auth:otp"
    AUTH_OTP_ATTEMPTS = "sk:auth:otp_attempts"
    CONTRACT_OTP = "sk:contract:otp"
    CONTRACT_OTP_ATTEMPTS = "sk:contract:otp_attempts"
    AUTH_SESSION = "sk:auth:session"
    AUTH_ADMIN_SESSION = "sk:auth:admin_session"
    CREDIT_USER = "sk:credit:user"
    CREDIT_VELOCITY = "sk:credit:velocity"
    CREDIT_BLACKLIST = "sk:credit:blacklist"
    PRODUCT_UPO = "sk:product:upo"
    PRODUCT_URL = "sk:product:url"
    KYC_NADRA = "sk:kyc:nadra"
    VCN_PENDING = "sk:vcn:pending"
    PAYMENT_IDEMPOTENT = "sk:payment:idempotent"
    WEBHOOK_DEDUP = "sk:webhook:dedup"
    SHIPMENT_TRACKING = "sk:shipment:tracking"
    FEATURE_FLAG = "sk:system:feature"
    RATE_LIMIT = "sk:ratelimit"
    LOCK = "sk:lock"

class QueueName:
    CHECKOUT = "sk:queue:checkout"
    SCRAPING = "sk:queue:scraping"
    # Compatibility alias used by gateway audit plan wording.
    PRODUCT_EXTRACT = "sk:queue:scraping"
    PAYMENT_INITIATE = "sk:queue:payment_initiate"
    PAYMENT_WEBHOOK = "sk:queue:payment_webhook"
    VCN_ISSUE = "sk:queue:vcn_issue"
    BILLING_SWEEP = "sk:queue:billing_sweep"
    BILLING_RETRY = "sk:queue:billing_retry"
    NOTIFICATION_SMS = "sk:queue:notification_sms"
    # Generic notification alias for publishers that do not choose a channel.
    NOTIFICATION = "sk:queue:notification_sms"
    NOTIFICATION_PUSH = "sk:queue:notification_push"
    NOTIFICATION_EMAIL = "sk:queue:notification_email"
    NOTIFICATION_WHATSAPP = "sk:queue:notification_whatsapp"
    KYC_PROCESS = "sk:queue:kyc_process"
    CREDIT_ASSESS = "sk:queue:credit_assess"
    HITL_ESCALATION = "sk:queue:hitl_escalation"
    WEBHOOK_DELIVERY = "sk:queue:webhook_delivery"
    RECONCILIATION = "sk:queue:reconciliation"
    CHARITY_DISBURSE = "sk:queue:charity_disburse"
    TRACKING_REGISTER = "sk:queue:tracking_register"
    VCN_VERIFICATION = "sk:queue:vcn_verification"

class RedisTTL:
    OTP = 180
    OTP_LOCKOUT = 300
    SESSION = 86400
    ADMIN_SESSION = 28800
    CREDIT_CACHE = 30
    PRODUCT_CACHE = 300
    PRODUCT_URL_MAP = 86400
    NADRA_CACHE = 2592000
    FEATURE_FLAG = 60
    FRAUD_RULES = 1800
    WEBHOOK_DEDUP = 86400
