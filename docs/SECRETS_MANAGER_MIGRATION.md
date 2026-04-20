# AWS Secrets Manager Migration Guide

**Purpose**: Migrate from environment variables in `.env` files to AWS Secrets Manager for automatic secret rotation, audit logging, and multi-region replication.

**Status**: Production-ready implementation guidance (requires AWS infrastructure)

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Step 1: AWS Setup](#step-1-aws-setup)
3. [Step 2: Create Secrets in Secrets Manager](#step-2-create-secrets-in-secrets-manager)
4. [Step 3: Update Ledger Config](#step-3-update-ledger-config)
5. [Step 4: Deploy with IAM Permissions](#step-4-deploy-with-iam-permissions)
6. [Step 5: Rotation Policies](#step-5-rotation-policies)
7. [Rollback Plan](#rollback-plan)
8. [Monitoring & Auditing](#monitoring--auditing)

---

## Architecture Overview

```
Environment (.env file)          AWS Secrets Manager              Application
┌─────────────────────┐         ┌─────────────────────┐          ┌──────────┐
│ DATABASE_URL        │         │ ledger/prod/db-url  │◄─────────│  Config  │
│ REDIS_URL           │  ──────►│ ledger/prod/redis   │          │ Loader   │
│ TASDEEQ_API_TOKEN   │  (move) │ ledger/prod/api-key │◄─────────│ at Boot  │
│ ...                 │         │ ...                 │          │          │
└─────────────────────┘         └─────────────────────┘          └──────────┘
                                        │
                                        │ Automated Rotation
                                        ▼
                            Lambda Function (optional)
                            ┌──────────────────────┐
                            │ Rotate Credentials   │
                            │ Every 30/60 days     │
                            └──────────────────────┘
```

### Benefits

- ✅ **Centralized Secrets**: Single source of truth for all credentials
- ✅ **Automatic Rotation**: Rotate DB passwords, API keys without app restart
- ✅ **Audit Trail**: CloudTrail logs all secret access and modifications
- ✅ **Encryption**: Secrets encrypted at rest with AWS KMS
- ✅ **Multi-Region**: Replicable to secondary regions for DR
- ✅ **Least Privilege**: IAM policies control who can read which secrets

### Tradeoffs

- ⚠️ **AWS Dependency**: Requires AWS infrastructure (no local-only mode)
- ⚠️ **Latency**: First call to retrieve secrets adds 10-50ms at boot
- ⚠️ **Cost**: ~$0.40 per secret per month + API call costs
- ⚠️ **Complexity**: Requires IAM setup and rotation Lambda functions

---

## Step 1: AWS Setup

### Prerequisites

```bash
# Install AWS CLI v2
# https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html

# Verify you have access
aws sts get-caller-identity
```

### Create Secret Folder Structure

We'll organize secrets by environment and service:

```
ledger/prod/
  ├── database-url
  ├── redis-url
  ├── redis-db
  ├── tasdeeq-api-token
  ├── internal-api-token
  └── payment-service-url

ledger/staging/
  ├── database-url
  ├── redis-url
  └── ...
```

---

## Step 2: Create Secrets in Secrets Manager

### Create Database URL Secret

```bash
aws secretsmanager create-secret \
  --name ledger/prod/database-url \
  --description "PostgreSQL connection string for Ledger Service" \
  --secret-string "postgresql+asyncpg://user:password@postgres.sahulatkar.internal:5432/ledger_prod" \
  --tags Key=Environment,Value=prod Key=Service,Value=ledger \
  --region us-east-1
```

### Create Redis URL Secret

```bash
aws secretsmanager create-secret \
  --name ledger/prod/redis-url \
  --description "Redis connection string" \
  --secret-string "redis://redis.sahulatkar.internal:6379" \
  --tags Key=Environment,Value=prod Key=Service,Value=ledger \
  --region us-east-1
```

### Create API Token Secret

```bash
aws secretsmanager create-secret \
  --name ledger/prod/tasdeeq-api-token \
  --description "TASDEEQ credit bureau API token" \
  --secret-string "your-tasdeeq-api-token-here" \
  --tags Key=Environment,Value=prod Key=Service,Value=ledger \
  --region us-east-1
```

### Create Internal API Token Secret

```bash
aws secretsmanager create-secret \
  --name ledger/prod/internal-api-token \
  --description "Internal service-to-service auth token" \
  --secret-string "$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  --tags Key=Environment,Value=prod Key=Service,Value=ledger \
  --region us-east-1
```

### Bulk Import Script

```python
#!/usr/bin/env python3
"""Bulk import .env file to AWS Secrets Manager"""

import json
import subprocess
import sys
from pathlib import Path

def import_env_to_secrets(env_file: str, environment: str = "prod", region: str = "us-east-1"):
    """
    Import .env file variables to Secrets Manager.
    
    Args:
        env_file: Path to .env file
        environment: Environment name (prod/staging/dev)
        region: AWS region
    """
    env_path = Path(env_file)
    if not env_path.exists():
        print(f"ERROR: {env_file} not found")
        return False
    
    secrets_created = 0
    secrets_failed = 0
    
    with env_path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            if "=" not in line:
                continue
            
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            
            # Convert key to secret name (e.g., DATABASE_URL → database-url)
            secret_name = f"ledger/{environment}/{key.lower().replace('_', '-')}"
            
            print(f"Creating secret: {secret_name}")
            
            try:
                cmd = [
                    "aws", "secretsmanager", "create-secret",
                    "--name", secret_name,
                    "--secret-string", value,
                    "--tags", f"Key=Environment,Value={environment}",
                    "--tags", "Key=Service,Value=ledger",
                    "--region", region,
                ]
                subprocess.run(cmd, check=True, capture_output=True)
                secrets_created += 1
            except subprocess.CalledProcessError as e:
                print(f"  ERROR: {e.stderr.decode()}")
                secrets_failed += 1
    
    print(f"\nImport complete: {secrets_created} created, {secrets_failed} failed")
    return secrets_failed == 0

if __name__ == "__main__":
    env_file = sys.argv[1] if len(sys.argv) > 1 else ".env"
    environment = sys.argv[2] if len(sys.argv) > 2 else "prod"
    success = import_env_to_secrets(env_file, environment)
    sys.exit(0 if success else 1)
```

---

## Step 3: Update Ledger Config

### Current Implementation (Environment Variables)

```python
# src/config.py (current)
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    redis_db: int
    tasdeeq_api_token: str
    internal_api_token: str
    payment_service_url: str
    # ...
    
    class Config:
        env_file = ".env"
```

### New Implementation (AWS Secrets Manager)

```python
# src/config.py (updated)
from pydantic_settings import BaseSettings
import boto3
import json
from functools import lru_cache

class Settings(BaseSettings):
    """
    Configuration with AWS Secrets Manager support.
    
    Behavior:
    1. First tries to load from AWS Secrets Manager (if AWS_REGION set)
    2. Falls back to environment variables
    3. Falls back to .env file
    
    This enables seamless migration: start with .env, upgrade to Secrets Manager
    without code changes.
    """
    
    database_url: str
    redis_url: str
    redis_db: int = 4
    tasdeeq_api_token: str
    tasdeeq_mode: str = "batch_csv"
    tasdeeq_endpoint_url: str = ""
    internal_api_token: str
    payment_service_url: str
    reconciliation_audit_dir: str = "/var/audit/reconciliation"
    tasdeeq_audit_dir: str = "/var/audit/tasdeeq"
    billing_sweep_cron: str = "0 2 * * *"  # 2 AM daily
    default_charity_registration_number: str = ""
    
    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache(maxsize=1)
def get_secrets_manager_client():
    """Cached Secrets Manager client."""
    return boto3.client("secretsmanager", region_name="us-east-1")

async def load_settings_from_secrets_manager(
    environment: str = "prod",
    region: str = "us-east-1",
) -> Settings:
    """
    Load settings from AWS Secrets Manager.
    
    Args:
        environment: Environment name (prod/staging/dev)
        region: AWS region
        
    Returns:
        Settings object populated from Secrets Manager
        
    Raises:
        ValueError: If secrets not found
    """
    import os
    
    client = boto3.client("secretsmanager", region_name=region)
    
    # List of (secret_name_in_manager, env_var_name)
    secret_mappings = [
        ("database-url", "DATABASE_URL"),
        ("redis-url", "REDIS_URL"),
        ("redis-db", "REDIS_DB"),
        ("tasdeeq-api-token", "TASDEEQ_API_TOKEN"),
        ("tasdeeq-mode", "TASDEEQ_MODE"),
        ("tasdeeq-endpoint-url", "TASDEEQ_ENDPOINT_URL"),
        ("internal-api-token", "INTERNAL_API_TOKEN"),
        ("payment-service-url", "PAYMENT_SERVICE_URL"),
        ("billing-sweep-cron", "BILLING_SWEEP_CRON"),
    ]
    
    loaded_secrets = {}
    failed_secrets = []
    
    for secret_name_key, env_var_name in secret_mappings:
        try:
            secret_name = f"ledger/{environment}/{secret_name_key}"
            response = client.get_secret_value(SecretId=secret_name)
            
            # Support both plain string and JSON secrets
            try:
                secret_value = json.loads(response["SecretString"])
                if isinstance(secret_value, dict):
                    loaded_secrets.update(secret_value)
                else:
                    loaded_secrets[env_var_name] = secret_value
            except json.JSONDecodeError:
                loaded_secrets[env_var_name] = response["SecretString"]
        except client.exceptions.ResourceNotFoundException:
            failed_secrets.append(secret_name_key)
        except Exception as e:
            raise ValueError(f"Failed to load secret {secret_name_key}: {str(e)}")
    
    if failed_secrets:
        raise ValueError(f"Missing secrets in Secrets Manager: {', '.join(failed_secrets)}")
    
    # Create settings object with loaded secrets
    return Settings(**loaded_secrets)

# Export settings
def get_settings() -> Settings:
    """Get settings, trying Secrets Manager first, then env vars."""
    import os
    
    # If AWS_REGION set, try Secrets Manager
    if os.getenv("AWS_REGION"):
        try:
            environment = os.getenv("ENVIRONMENT", "prod")
            import asyncio
            settings = asyncio.run(load_settings_from_secrets_manager(
                environment=environment,
                region=os.getenv("AWS_REGION", "us-east-1"),
            ))
            return settings
        except ValueError as e:
            print(f"WARNING: Failed to load from Secrets Manager: {e}")
            # Fall through to env var loading
    
    # Fall back to environment variables and .env file
    return Settings()

settings = get_settings()
```

---

## Step 4: Deploy with IAM Permissions

### Create IAM Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:us-east-1:ACCOUNT-ID:secret:ledger/prod/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt"
      ],
      "Resource": "arn:aws:kms:us-east-1:ACCOUNT-ID:key/KEY-ID",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "secretsmanager.us-east-1.amazonaws.com"
        }
      }
    }
  ]
}
```

### Attach to EKS Pod Role

```bash
# Get current pod role
ROLE_NAME=$(aws iam list-roles --query "Roles[?contains(AssumeRolePolicyDocument, 'eks.amazonaws.com')].RoleName" --output text)

# Create policy
aws iam put-role-policy \
  --role-name $ROLE_NAME \
  --policy-name ledger-secrets-manager \
  --policy-document file://policy.json
```

### Update K8s Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ledger-service
spec:
  template:
    spec:
      serviceAccountName: ledger-service
      containers:
      - name: ledger-service
        image: sahulatkar/ledger-service:latest
        env:
        - name: AWS_REGION
          value: "us-east-1"
        - name: ENVIRONMENT
          value: "prod"
        # Do NOT include sensitive vars here anymore
```

---

## Step 5: Rotation Policies

### Automatic Database Password Rotation

```bash
# Create rotation Lambda (example pseudocode)
aws secretsmanager rotate-secret \
  --secret-id ledger/prod/database-url \
  --rotation-rules AutomaticallyAfterDays=30
```

### Lambda Rotation Function

```python
import boto3
import psycopg2
import json

def rotate_database_password(event, context):
    """Rotate PostgreSQL password in Secrets Manager and database."""
    
    client = boto3.client("secretsmanager")
    secret_id = event["ClientRequestToken"]
    
    try:
        # Get current secret
        current = client.get_secret_value(SecretId=secret_id, VersionId=event["ClientRequestToken"], VersionStage="AWSCURRENT")
        current_secret = json.loads(current["SecretString"])
        
        # Generate new password
        import secrets
        new_password = secrets.token_urlsafe(32)
        
        # Update database
        conn = psycopg2.connect(
            host=current_secret["host"],
            user=current_secret["username"],
            password=current_secret["password"],
            database="postgres",
        )
        cursor = conn.cursor()
        cursor.execute(f"ALTER USER {current_secret['username']} WITH PASSWORD %s", (new_password,))
        conn.commit()
        
        # Update secret
        new_secret = {**current_secret, "password": new_password}
        client.put_secret_value(
            SecretId=secret_id,
            SecretString=json.dumps(new_secret),
            VersionStages=["AWSCURRENT"],
        )
        
        print(f"Successfully rotated password for {secret_id}")
    except Exception as e:
        raise Exception(f"Rotation failed: {str(e)}")
```

---

## Rollback Plan

### If Secrets Manager Fails

1. **Keep .env file as backup**
   ```bash
   # Check .env exists before deploying
   git add infra/.env.prod
   git commit -m "backup: .env for rollback"
   ```

2. **Disable Secrets Manager loading**
   ```bash
   # Remove AWS_REGION env var from deployment
   # Service will fall back to .env file
   kubectl set env deployment/ledger-service AWS_REGION- -n sahulatkar
   ```

3. **Redeploy with previous config**
   ```bash
   kubectl rollout undo deployment/ledger-service -n sahulatkar
   ```

---

## Monitoring & Auditing

### CloudTrail Logging

```bash
# Enable CloudTrail for Secrets Manager
aws cloudtrail put-event-selectors \
  --trail-name sahulatkar-trail \
  --event-selectors ReadWriteType=All,IncludeManagementEvents=true
```

### CloudWatch Metrics

```python
import boto3

cloudwatch = boto3.client("cloudwatch")

# Log secret access
cloudwatch.put_metric_data(
    Namespace="Ledger/SecretsManager",
    MetricData=[
        {
            "MetricName": "SecretRetrievals",
            "Value": 1,
            "Unit": "Count",
            "Dimensions": [
                {"Name": "SecretName", "Value": "ledger/prod/database-url"}
            ],
        }
    ]
)
```

### Audit Dashboard

Create CloudWatch dashboard:

```json
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/SecretsManager", "SecretCount", {"stat": "Average"}],
          [".", "RotationCount", {"stat": "Sum"}],
          [".", "AccessDeniedCount", {"stat": "Sum"}]
        ],
        "period": 300,
        "stat": "Average",
        "region": "us-east-1",
        "title": "Secrets Manager Activity"
      }
    }
  ]
}
```

---

## Implementation Checklist

- [ ] Create AWS IAM role with Secrets Manager permissions
- [ ] Create secrets in Secrets Manager for prod/staging
- [ ] Update `config.py` with Secrets Manager loader
- [ ] Test locally with `AWS_REGION` env var set
- [ ] Update K8s deployment manifests
- [ ] Deploy to staging environment
- [ ] Verify all services access secrets correctly
- [ ] Monitor logs for 24 hours
- [ ] Deploy to production
- [ ] Archive .env file (keep for 30 days backup)
- [ ] Set up automatic rotation policies
- [ ] Configure CloudTrail auditing

---

## Cost Estimation

| Item | Cost |
|------|------|
| Secrets per month | $0.40 × 15 secrets = $6/month |
| API calls (10M/month) | $0.05 per million × 10 = $0.50 |
| KMS key (optional) | $1.00 |
| **Total** | **~$8/month** |

For pricing details, see [AWS Secrets Manager Pricing](https://aws.amazon.com/secrets-manager/pricing/)

---

## References

- [AWS Secrets Manager Documentation](https://docs.aws.amazon.com/secretsmanager/)
- [Rotate Secrets](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html)
- [IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
