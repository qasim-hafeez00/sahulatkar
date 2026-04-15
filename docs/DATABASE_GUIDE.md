# SahulatKar Database Connection Guide

This guide contains the credentials and configuration necessary to connect to the SahulatKar development database.

## 🗄️ Connection Credentials

| Detail | Value |
| :--- | :--- |
| **Host** | `localhost` (or `127.0.0.1`) |
| **Port** | `5432` |
| **Maintenance Database** | `postgres` |
| **Target Database** | `sahulatkar` |
| **Primary Admin User** | `sk_admin` |
| **Admin Password** | `localdev123` |

---

## 🔑 Database Roles
The following roles are pre-configured for different services:

| Role Name | Access Level | Description |
| :--- | :--- | :--- |
| `sk_migrations` | **Superuser** | Used for running migrations/Alembic. |
| `sk_app` | Read/Write | Main backend application user. |
| `sk_admin_api` | Read/Write | Admin dashboard backend user. |
| `sk_app_readonly` | Read Only | For data visualization and reporting tools. |

> [!NOTE]
> All roles currently use the default password: `localdev123`

---

## 🛠️ Commands & Management

### Starting the Database
If the database is not running, use this command from the project root:
```powershell
docker-compose -f infra/docker/docker-compose.yml up -d postgres
```

### Accessing via Command Line (CLI)
You can enter the database directly via terminal using:
```powershell
docker exec -it sk-postgres psql -U sk_admin -d sahulatkar
```

---

## ⚠️ Troubleshooting: Connection Issues

### "Role sk_admin does not exist"
If you see this error while Docker is running, it means a local PostgreSQL service is already running on your Windows machine and occupying port **5432**.

**Fix:** Stop the local Windows service to allow Docker to use the port:
1. Open PowerShell as Administrator.
2. Run: `Stop-Service postgresql-x64-17` (or whichever version is installed).

### "SERVICE_NAME variable not set"
This warning occurs during `docker-compose` if the `.env` file is missing. The system will default to local values, but for production-like testing, ensure a `.env` file exists in the root directory.
