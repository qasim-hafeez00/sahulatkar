"""
Seeds a full set of dev-only accounts: one admin per RBAC role, and several
customer users with an approved KYC profile ("confirmed") so the dashboard,
credit gauge, and order flows have real data to render against instead of
the "Pending verification" placeholder state.

Every seeded credential is written to SEEDED_ACCOUNTS.md at the repo root
(gitignored) so they don't need to be re-derived by reading this file.

Run: python scripts/seed_dev_users.py
"""
import asyncio
import datetime
import sys
import os
import uuid

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("packages/shared-python"))
sys.path.insert(0, os.path.abspath("apps/gateway"))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from sk_shared.security import get_password_hash
from src.core.kms import KMSProvider  # apps/gateway's AES-256-GCM mock KMS — same encryption the KYC service uses

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://sk_admin:localdev123@localhost:5434/sahulatkar")

ROLES = [
    ("super_admin", "Full system access and super admin capabilities"),
    ("operations_manager", "Day-to-day operations: users, orders, payments"),
    ("risk_officer", "Risk, fraud, and credit underwriting oversight"),
    ("compliance_officer", "Regulatory compliance, KYC review, audit trail"),
    ("finance_analyst", "Financial reporting, reconciliation, payments"),
    ("analyst", "Cross-functional reporting and analytics"),
    ("marketing_manager", "Marketing campaigns and partner analytics"),
    ("cs_agent", "Customer support agent"),
]

# One admin per role so every RBAC-gated web-admin screen has a real login to test with.
ADMINS = [
    {"role": "super_admin", "email": "admin@sahulatkar.com", "password": "AdminPassword123!"},
    {"role": "operations_manager", "email": "ops@sahulatkar.com", "password": "AdminPass123!"},
    {"role": "risk_officer", "email": "risk@sahulatkar.com", "password": "AdminPass123!"},
    {"role": "compliance_officer", "email": "compliance@sahulatkar.com", "password": "AdminPass123!"},
    {"role": "finance_analyst", "email": "finance@sahulatkar.com", "password": "AdminPass123!"},
    {"role": "analyst", "email": "analyst@sahulatkar.com", "password": "AdminPass123!"},
    {"role": "marketing_manager", "email": "marketing@sahulatkar.com", "password": "AdminPass123!"},
    {"role": "cs_agent", "email": "support@sahulatkar.com", "password": "AdminPass123!"},
]

# Customers seeded with an approved KYC verification ("confirmed") plus a
# credit_limit/available_credit split so the Dashboard's utilization gauge
# and upcoming-installment cards have something real to show.
CUSTOMERS = [
    {
        "phone": "+923001234567",
        "password": "CustomerPassword123!",
        "first_name": "Ayesha",
        "last_name": "Siddiqui",
        "cnic": "35202-1234567-1",
        "dob": datetime.datetime(1996, 4, 12),
        "address": "House 12, Street 5, F-10/2, Islamabad",
        "credit_limit": 250000.00,
        "available_credit": 175000.00,
    },
    {
        "phone": "+923001234568",
        "password": "CustomerPassword123!",
        "first_name": "Bilal",
        "last_name": "Ahmed",
        "cnic": "42101-2345678-3",
        "dob": datetime.datetime(1992, 11, 3),
        "address": "Flat 4B, Clifton Block 2, Karachi",
        "credit_limit": 150000.00,
        "available_credit": 150000.00,
    },
    {
        "phone": "+923001234569",
        "password": "CustomerPassword123!",
        "first_name": "Sana",
        "last_name": "Tariq",
        "cnic": "35201-3456789-5",
        "dob": datetime.datetime(1998, 7, 21),
        "address": "House 88, Model Town, Lahore",
        "credit_limit": 400000.00,
        "available_credit": 90000.00,
    },
    {
        "phone": "+923001234570",
        "password": "CustomerPassword123!",
        "first_name": "Usman",
        "last_name": "Malik",
        "cnic": "37405-4567891-7",
        "dob": datetime.datetime(1990, 1, 30),
        "address": "Street 9, Cantt, Rawalpindi",
        "credit_limit": 100000.00,
        "available_credit": 100000.00,
    },
    {
        "phone": "+923001234571",
        "password": "CustomerPassword123!",
        "first_name": "Hira",
        "last_name": "Farooq",
        "cnic": "42201-5678912-9",
        "dob": datetime.datetime(1995, 9, 15),
        "address": "Gulshan-e-Iqbal Block 6, Karachi",
        "credit_limit": 300000.00,
        "available_credit": 300000.00,
    },
]


async def seed_data() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    kms = KMSProvider()

    seeded_admins = []
    seeded_customers = []

    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP;"))

        # 1. Roles
        for role_name, desc in ROLES:
            await conn.execute(text("""
                INSERT INTO roles (name, description)
                VALUES (:name, :desc)
                ON CONFLICT (name) DO NOTHING;
            """), {"name": role_name, "desc": desc})

        role_ids: dict[str, int] = {}
        for role_name, _ in ROLES:
            res = await conn.execute(text("SELECT id FROM roles WHERE name = :name;"), {"name": role_name})
            role_ids[role_name] = res.fetchone()[0]

        # 2. Admins — one per role
        for admin in ADMINS:
            hashed = get_password_hash(admin["password"])
            role_id = role_ids[admin["role"]]
            res = await conn.execute(text("SELECT id FROM admin_users WHERE email = :email;"), {"email": admin["email"]})
            if res.fetchone() is None:
                await conn.execute(text("""
                    INSERT INTO admin_users (uuid, email, password_hash, mfa_enabled, force_password_change, role_id, created_at, updated_at)
                    VALUES (:uuid, :email, :password_hash, false, false, :role_id, NOW(), NOW());
                """), {
                    "uuid": str(uuid.uuid4()),
                    "email": admin["email"],
                    "password_hash": hashed,
                    "role_id": role_id,
                })
            else:
                await conn.execute(text("""
                    UPDATE admin_users
                    SET password_hash = :password_hash, mfa_enabled = false, force_password_change = false, role_id = :role_id, updated_at = NOW()
                    WHERE email = :email;
                """), {"email": admin["email"], "password_hash": hashed, "role_id": role_id})
            seeded_admins.append({"role": admin["role"], "email": admin["email"], "password": admin["password"]})

        # 3. Customers + KYC profile + approved verification
        for cust in CUSTOMERS:
            hashed = get_password_hash(cust["password"])
            res = await conn.execute(text("SELECT id FROM users WHERE phone = :phone;"), {"phone": cust["phone"]})
            row = res.fetchone()

            if row is None:
                res = await conn.execute(text("""
                    INSERT INTO users (uuid, phone, first_name, last_name, password_hash, status,
                                        failed_login_attempts, credit_limit, available_credit,
                                        created_at, updated_at)
                    VALUES (:uuid, :phone, :first_name, :last_name, :password_hash, 'active',
                            0, :credit_limit, :available_credit, NOW(), NOW())
                    RETURNING id;
                """), {
                    "uuid": str(uuid.uuid4()),
                    "phone": cust["phone"],
                    "first_name": cust["first_name"],
                    "last_name": cust["last_name"],
                    "password_hash": hashed,
                    "credit_limit": cust["credit_limit"],
                    "available_credit": cust["available_credit"],
                })
                user_id = res.fetchone()[0]
            else:
                user_id = row[0]
                await conn.execute(text("""
                    UPDATE users
                    SET password_hash = :password_hash, status = 'active', failed_login_attempts = 0,
                        first_name = :first_name, last_name = :last_name,
                        credit_limit = :credit_limit, available_credit = :available_credit,
                        updated_at = NOW()
                    WHERE id = :user_id;
                """), {
                    "password_hash": hashed,
                    "first_name": cust["first_name"],
                    "last_name": cust["last_name"],
                    "credit_limit": cust["credit_limit"],
                    "available_credit": cust["available_credit"],
                    "user_id": user_id,
                })

            encrypted_cnic = kms.encrypt(cust["cnic"])
            res = await conn.execute(text("SELECT id FROM customer_profiles WHERE user_id = :user_id;"), {"user_id": user_id})
            if res.fetchone() is None:
                await conn.execute(text("""
                    INSERT INTO customer_profiles (uuid, user_id, first_name, last_name, cnic, dob, address, created_at, updated_at)
                    VALUES (:uuid, :user_id, :first_name, :last_name, :cnic, :dob, :address, NOW(), NOW());
                """), {
                    "uuid": str(uuid.uuid4()),
                    "user_id": user_id,
                    "first_name": cust["first_name"],
                    "last_name": cust["last_name"],
                    "cnic": encrypted_cnic,
                    "dob": cust["dob"],
                    "address": cust["address"],
                })
            else:
                await conn.execute(text("""
                    UPDATE customer_profiles
                    SET first_name = :first_name, last_name = :last_name, cnic = :cnic,
                        dob = :dob, address = :address, updated_at = NOW()
                    WHERE user_id = :user_id;
                """), {
                    "first_name": cust["first_name"],
                    "last_name": cust["last_name"],
                    "cnic": encrypted_cnic,
                    "dob": cust["dob"],
                    "address": cust["address"],
                    "user_id": user_id,
                })

            res = await conn.execute(text("""
                SELECT id FROM user_kyc_verifications WHERE user_id = :user_id AND status = 'approved';
            """), {"user_id": user_id})
            if res.fetchone() is None:
                await conn.execute(text("""
                    INSERT INTO user_kyc_verifications (uuid, user_id, status, nadra_verified_at, created_at, updated_at)
                    VALUES (:uuid, :user_id, 'approved', NOW(), NOW(), NOW());
                """), {"uuid": str(uuid.uuid4()), "user_id": user_id})

            seeded_customers.append({
                "name": f"{cust['first_name']} {cust['last_name']}",
                "phone": cust["phone"],
                "password": cust["password"],
                "credit_limit": cust["credit_limit"],
            })

    await engine.dispose()
    write_credentials_file(seeded_admins, seeded_customers)
    print(f"\nSeeded {len(seeded_admins)} admins and {len(seeded_customers)} KYC-confirmed customers.")
    print("Credentials written to SEEDED_ACCOUNTS.md at the repo root.")


def write_credentials_file(admins: list[dict], customers: list[dict]) -> None:
    lines = [
        "# Seeded Dev Accounts",
        "",
        "> Auto-generated by `scripts/seed_dev_users.py`. Local/dev database only —",
        "> never commit real credentials here. This file is gitignored.",
        "",
        f"Last seeded: {datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')}",
        "",
        "## Admins (web-admin, one per role)",
        "",
        "| Role | Email | Password |",
        "|---|---|---|",
    ]
    for a in admins:
        lines.append(f"| {a['role']} | {a['email']} | {a['password']} |")

    lines += [
        "",
        "## Customers (web-customer, KYC-approved)",
        "",
        "| Name | Phone | Password | Credit Limit (PKR) |",
        "|---|---|---|---|",
    ]
    for c in customers:
        lines.append(f"| {c['name']} | {c['phone']} | {c['password']} | {c['credit_limit']:,.0f} |")

    lines.append("")
    root = os.path.abspath(".")
    with open(os.path.join(root, "SEEDED_ACCOUNTS.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(seed_data())
