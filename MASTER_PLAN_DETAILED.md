# SAHULATKAR — MASTER PLAN: DETAILED TECHNICAL SPECIFICATIONS

> **Companion to**: `MASTER_PLAN.md` (paste BOTH files into new chat sessions)
> **Last Updated**: 2026-04-08

---

## TABLE OF CONTENTS

1. [Inter-Service Communication Map](#1-inter-service-communication-map)
2. [Full Database Migration Sequence](#2-full-database-migration-sequence)
3. [Complete Model Registry](#3-complete-model-registry)
4. [Redis Key Architecture](#4-redis-key-architecture)
5. [BullMQ Worker Architecture](#5-bullmq-worker-architecture)
6. [K8s Manifest Templates](#6-k8s-manifest-templates)
7. [Terraform Resource Specs](#7-terraform-resource-specs)
8. [CI/CD Pipeline — Production YAML](#8-cicd-pipeline--production-yaml)
9. [Frontend Page Breakdown](#9-frontend-page-breakdown)
10. [Deployment Runbook](#10-deployment-runbook)
11. [Rollback Procedures](#11-rollback-procedures)
12. [Data Seeding Strategy](#12-data-seeding-strategy)
13. [API Versioning Strategy](#13-api-versioning-strategy)
14. [Error Code Registry](#14-error-code-registry)
15. [Performance Budgets](#15-performance-budgets)

---

## 1. INTER-SERVICE COMMUNICATION MAP

### Synchronous (HTTP REST — internal)

```
Gateway ──GET /credit/check──────────► Credit Engine
Gateway ──POST /vcn/issue────────────► Payment Orchestrator
Gateway ──POST /products/extract─────► Product Service
Gateway ──POST /tracking/register────► Notification Service
Gateway ──GET /ledger/balance────────► Ledger Service
```

### Asynchronous (Redis Pub/Sub Events)

```
Product Service ──"product.extracted"──────────► Gateway (updates order)
Payment Orch.   ──"payment.down_payment_confirmed"──► Payment Orch. (VCN issue)
Payment Orch.   ──"vcn.issued"─────────────────► Product Service (checkout agent)
Product Service ──"order.purchase_confirmed"───► Gateway + Ledger + Notification
Notification    ──"delivery.status_changed"────► Gateway + Ledger
Ledger          ──"installment.paid"───────────► Notification
Ledger          ──"installment.overdue"────────► Notification + Gateway
```

### Event Payload Standards

Every event follows this envelope:

```python
# packages/shared-python/sk_shared/events.py
@dataclass
class EventEnvelope:
    event: str              # "product.extracted"
    event_id: str           # UUID — idempotency key
    timestamp: str          # ISO8601
    source_service: str     # "product-service"
    correlation_id: str     # Traces across services (from X-Request-ID)
    payload: dict           # Event-specific data

# Publishing pattern
await redis.publish(f"sk:events:{event_name}", json.dumps(envelope))

# Subscribing pattern (each service runs a listener coroutine)
pubsub = redis.pubsub()
await pubsub.subscribe("sk:events:product.extracted")
```

### Service Dependency Matrix

| Service | Depends On (must be running) |
|---|---|
| Gateway | PostgreSQL, Redis, all other services (routes to them) |
| Product Service | PostgreSQL, Redis, BrightData (external), Groq (external) |
| Credit Engine | PostgreSQL, Redis |
| Payment Orchestrator | PostgreSQL, Redis, Stripe (external), Safepay (ext), JazzCash (ext) |
| Ledger Service | PostgreSQL, Redis |
| Notification Service | PostgreSQL, Redis, Jazz SMS (ext), Firebase (ext), SendGrid (ext) |

---

## 2. FULL DATABASE MIGRATION SEQUENCE

All migrations live in `db/migrations/versions/`. Order matters.

| # | File | Module | Tables Created |
|---|---|---|---|
| 001 | `001_init_m04.py` | Credit Engine | `credit_applications`, `risk_assessments`, `credit_limit_history`, `blacklisted_entities`, `fraud_rules`, `velocity_checks` |
| 002 | `002_init_m01_auth.py` | Auth | `users`, `admin_users`, `user_sessions`, `user_devices`, `roles`, `permissions`, `role_permissions` |
| 003 | `003_init_m02_kyc.py` | KYC | `user_kyc_verifications`, `kyc_verification_queue` |
| 004 | `004_init_m03_products.py` | Products | `products`, `scraping_jobs`, `merchants`, `prohibited_categories`, `prohibited_items_log` |
| 005 | `005_init_m05_contracts.py` | Contracts | `wakalah_agreements`, `murabaha_contracts`, `contract_digital_signatures` |
| 006 | `006_init_m06_payments.py` | Payments | `loans`, `installments`, `payment_transactions`, `payment_methods`, `virtual_cards` |
| 007 | `007_init_m08_checkout.py` | Checkout | `purchase_executions` |
| 008 | `008_init_m09_hitl.py` | HITL | `hitl_queue` |
| 009 | `009_init_m10_delivery.py` | Delivery | `shipments`, `tracking_events`, `couriers` |
| 010 | `010_init_m11_ledger.py` | Ledger | `ledger_accounts`, `journal_entries`, `journal_entry_lines`, `late_fee_charity_allocations`, `charity_organizations` |
| 011 | `011_init_orders.py` | Orders | `orders` (partitioned quarterly), `order_status_history` |
| 012 | `012_init_audit.py` | Audit | `audit_trails` (partitioned monthly) |
| 013 | `013_init_system.py` | System | `system_settings`, `feature_flags`, `api_keys` |
| 014 | `014_triggers.py` | Triggers | `fn_apply_late_fee()`, `fn_recalculate_available_credit()`, audit triggers |
| 015 | `015_indexes.py` | Performance | Partial indexes, GIN indexes, composite indexes |
| 016 | `016_seed_data.py` | Seed | Roles, permissions, prohibited categories, ledger accounts, couriers |

### Migration Rules

- Every migration MUST have both `upgrade()` and `downgrade()`
- Test reversibility: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
- Never modify a committed migration — create a new one
- Use `op.execute()` for raw SQL (triggers, partitions)
- Partitioned tables use `postgresql_partition_by` in `__table_args__`

---

## 3. COMPLETE MODEL REGISTRY

### Shared Models (`packages/shared-python/sk_shared/models/`)

```
__init__.py          — re-exports all models
base.py              — Base, TimestampMixin, UUIDMixin, SoftDeleteMixin
auth.py              — User, AdminUser, UserSession, Role, Permission, RolePermission
kyc.py               — UserKycVerification, UserDevice, KycVerificationQueue
product.py           — Product, ScrapingJob, Merchant, ProhibitedCategory, ProhibitedItemLog
credit.py            — CreditApplication, RiskAssessment, CreditLimitHistory, BlacklistedEntity, FraudRule, VelocityCheck
contracts.py         — WakalahAgreement, MurabahaContract, ContractDigitalSignature
payment.py           — Loan, Installment, PaymentTransaction, PaymentMethod, VirtualCard
checkout.py          — PurchaseExecution
hitl.py              — HitlQueue
delivery.py          — Shipment, TrackingEvent, Courier
ledger.py            — LedgerAccount, JournalEntry, JournalEntryLine, LateFeeCharityAllocation, CharityOrganization
order.py             — Order, OrderStatusHistory
audit.py             — AuditTrail
system.py            — SystemSetting, FeatureFlag, ApiKey
```

### SoftDeleteMixin (add to base.py)

```python
class SoftDeleteMixin:
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    @hybrid_property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
```

### All models MUST use:
- `Base` as declarative base
- `TimestampMixin` for `created_at`, `updated_at`
- `UUIDMixin` for external-facing UUID
- `SoftDeleteMixin` for customer-facing tables
- `DECIMAL(14,2)` for monetary fields
- `BIGSERIAL` for internal PKs

---

## 4. REDIS KEY ARCHITECTURE

### Full Key Map

```python
# AUTH (Redis DB 0 — Gateway)
sk:auth:otp:{phone}:{type}           TTL=180s    # Hashed OTP code
sk:auth:otp_attempts:{phone}         TTL=300s    # Attempt counter
sk:auth:session:{token_hash}         TTL=86400s  # User session
sk:auth:admin_session:{token_hash}   TTL=28800s  # Admin session
sk:ratelimit:auth:{phone}            TTL=3600s   # Rate limit counter

# PRODUCT (Redis DB 1 — Product Service)
sk:product:upo:{product_uuid}        TTL=300s    # Cached UPO
sk:product:url:{url_hash}            TTL=86400s  # URL → product mapping (dedup)
sk:queue:scraping                     persistent  # BullMQ scraping jobs
sk:queue:checkout                     persistent  # BullMQ checkout jobs

# CREDIT (Redis DB 2 — Credit Engine)
sk:credit:user:{user_id}:limit       TTL=30s     # Cached credit limit
sk:credit:blacklist:{type}:{value}   TTL=none    # Blacklist set
sk:credit:velocity:{user_id}:{type}  TTL=varies  # Sliding window counters
sk:credit:portfolio:{category}       TTL=60s     # Portfolio concentration cache

# PAYMENT (Redis DB 3 — Payment Orchestrator)
sk:payment:idempotent:{key}          TTL=86400s  # Idempotency cache
sk:webhook:dedup:{hash}              TTL=86400s  # Webhook deduplication
sk:vcn:pending:{order_id}            TTL=86400s  # VCN issuance tracking
sk:queue:vcn_issue                    persistent  # BullMQ VCN queue
sk:queue:billing_sweep                persistent  # Daily billing jobs
sk:queue:billing_retry                persistent  # Payment retry queue

# LEDGER (Redis DB 4 — Ledger Service)
sk:queue:reconciliation               persistent  # Reconciliation jobs
sk:queue:charity_disburse              persistent  # Charity disbursement

# NOTIFICATION (Redis DB 5 — Notification Service)
sk:queue:notification_sms              persistent  # SMS queue
sk:queue:notification_push             persistent  # Push notification queue
sk:queue:notification_email            persistent  # Email queue
sk:queue:notification_whatsapp         persistent  # WhatsApp queue

# SYSTEM (shared)
sk:system:feature:{flag_name}        TTL=60s     # Feature flags
sk:lock:{resource}:{id}              TTL=30s     # Distributed locks (Redlock)
```

---

## 5. BULLMQ WORKER ARCHITECTURE

### Queue Consumer Pattern

```python
# packages/shared-python/sk_shared/worker.py
import asyncio, json, signal
from redis.asyncio import Redis

class BaseWorker:
    def __init__(self, queue_name: str, redis_url: str, concurrency: int = 5):
        self.queue = queue_name
        self.redis = Redis.from_url(redis_url)
        self.concurrency = concurrency
        self.running = True

    async def process(self, job_data: dict) -> dict:
        """Override in subclass"""
        raise NotImplementedError

    async def run(self):
        sem = asyncio.Semaphore(self.concurrency)
        while self.running:
            job = await self.redis.brpop(self.queue, timeout=5)
            if job:
                async with sem:
                    data = json.loads(job[1])
                    try:
                        result = await self.process(data)
                        await self._ack(data["job_id"], result)
                    except Exception as e:
                        await self._fail(data["job_id"], str(e))

    async def _ack(self, job_id, result): ...
    async def _fail(self, job_id, error): ...
```

### Workers Per Service

| Service | Worker | Queue | Concurrency | KEDA Trigger |
|---|---|---|---|---|
| Product Service | ScrapingWorker | sk:queue:scraping | 10 | queue length > 5 |
| Product Service | CheckoutWorker | sk:queue:checkout | 5 | queue length > 2 |
| Credit Engine | CreditAssessWorker | sk:queue:credit_assess | 20 | queue length > 10 |
| Payment Orch. | VcnIssueWorker | sk:queue:vcn_issue | 5 | queue length > 2 |
| Payment Orch. | BillingSweepWorker | sk:queue:billing_sweep | 10 | cron: 0 8 * * * |
| Payment Orch. | BillingRetryWorker | sk:queue:billing_retry | 5 | queue length > 5 |
| Ledger Service | ReconciliationWorker | sk:queue:reconciliation | 3 | cron: 0 2 * * * |
| Ledger Service | CharityWorker | sk:queue:charity_disburse | 2 | queue length > 1 |
| Notification | SmsWorker | sk:queue:notification_sms | 20 | queue length > 10 |
| Notification | PushWorker | sk:queue:notification_push | 20 | queue length > 10 |
| Notification | EmailWorker | sk:queue:notification_email | 10 | queue length > 5 |
| Notification | WhatsAppWorker | sk:queue:notification_whatsapp | 10 | queue length > 5 |

### Worker Deployment

Each worker runs as a separate K8s Deployment with its own HPA/KEDA ScaledObject:

```yaml
# infra/k8s/base/product-service/worker-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sk-product-checkout-worker
spec:
  replicas: 1  # KEDA manages scaling
  template:
    spec:
      containers:
        - name: worker
          image: ${ECR}/sk-product-service:latest
          command: ["python", "-m", "src.workers.checkout_consumer"]
          resources:
            requests: { cpu: "500m", memory: "1Gi" }
            limits:   { cpu: "2000m", memory: "4Gi" }  # Playwright needs RAM
```

---

## 6. K8S MANIFEST TEMPLATES

### Base Deployment Template

```yaml
# infra/k8s/base/{service}/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sk-{service}
  labels:
    app: sk-{service}
    tier: backend
spec:
  replicas: 2
  selector:
    matchLabels:
      app: sk-{service}
  template:
    metadata:
      labels:
        app: sk-{service}
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: sk-{service}
      containers:
        - name: app
          image: ${ECR_REGISTRY}/sk-{service}:latest
          ports:
            - containerPort: 8000
          envFrom:
            - secretRef:
                name: sk-{service}-secrets
            - configMapRef:
                name: sk-{service}-config
          readinessProbe:
            httpGet: { path: /health, port: 8000 }
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet: { path: /health, port: 8000 }
            initialDelaySeconds: 15
            periodSeconds: 20
          resources:
            requests: { cpu: "250m", memory: "512Mi" }
            limits:   { cpu: "1000m", memory: "1Gi" }
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
```

### Base Service Template

```yaml
# infra/k8s/base/{service}/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: sk-{service}
spec:
  selector:
    app: sk-{service}
  ports:
    - port: 8000
      targetPort: 8000
  type: ClusterIP
```

### HPA Template

```yaml
# infra/k8s/base/{service}/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: sk-{service}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: sk-{service}
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target: { type: Utilization, averageUtilization: 70 }
    - type: Resource
      resource:
        name: memory
        target: { type: Utilization, averageUtilization: 80 }
```

### KEDA ScaledObject (Checkout Agent)

```yaml
# infra/k8s/keda/checkout-agent-scaledobject.yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: sk-checkout-agent
spec:
  scaleTargetRef:
    name: sk-product-checkout-worker
  minReplicaCount: 0
  maxReplicaCount: 100
  pollingInterval: 15
  triggers:
    - type: redis
      metadata:
        address: sk-redis.sahulatkar.svc:6379
        listName: sk:queue:checkout
        listLength: "2"
        databaseIndex: "1"
      authenticationRef:
        name: sk-redis-auth
```

### Ingress (NGINX)

```yaml
# infra/k8s/base/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: sk-api-ingress
  annotations:
    nginx.ingress.kubernetes.io/rate-limit: "100"
    nginx.ingress.kubernetes.io/rate-limit-window: "1m"
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
    - hosts: [api.sahulatkar.com]
      secretName: sk-api-tls
  rules:
    - host: api.sahulatkar.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service: { name: sk-gateway, port: { number: 8000 } }
```

### Kustomization (Base)

```yaml
# infra/k8s/base/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: sahulatkar
resources:
  - gateway/deployment.yaml
  - gateway/service.yaml
  - gateway/hpa.yaml
  - product-service/deployment.yaml
  - product-service/service.yaml
  - product-service/hpa.yaml
  - credit-engine/deployment.yaml
  - credit-engine/service.yaml
  - credit-engine/hpa.yaml
  - payment-orchestrator/deployment.yaml
  - payment-orchestrator/service.yaml
  - payment-orchestrator/hpa.yaml
  - ledger-service/deployment.yaml
  - ledger-service/service.yaml
  - ledger-service/hpa.yaml
  - notification-service/deployment.yaml
  - notification-service/service.yaml
  - notification-service/hpa.yaml
  - pgbouncer/deployment.yaml
  - pgbouncer/service.yaml
  - ingress.yaml
```

### Staging Overlay

```yaml
# infra/k8s/overlays/staging/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
bases:
  - ../../base
patchesStrategicMerge:
  - patches/reduce-replicas.yaml
  - patches/reduce-resources.yaml
configMapGenerator:
  - name: sk-common-config
    literals:
      - ENV=staging
      - LOG_LEVEL=DEBUG
```

### Production Overlay

```yaml
# infra/k8s/overlays/production/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
bases:
  - ../../base
resources:
  - pod-disruption-budgets.yaml
patchesStrategicMerge:
  - patches/increase-replicas.yaml
configMapGenerator:
  - name: sk-common-config
    literals:
      - ENV=production
      - LOG_LEVEL=INFO
```

---

## 7. TERRAFORM RESOURCE SPECS

### VPC Module

```hcl
# infra/terraform/modules/vpc/main.tf
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.5.1"

  name = "sk-${var.environment}"
  cidr = "10.0.0.0/16"

  azs             = ["ap-south-1a", "ap-south-1b"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]
  database_subnets = ["10.0.201.0/24", "10.0.202.0/24"]

  enable_nat_gateway     = true
  single_nat_gateway     = var.environment == "staging"
  enable_dns_hostnames   = true
  create_database_subnet_group = true

  tags = { Project = "SahulatKar", Environment = var.environment }
}
```

### EKS Module

```hcl
# infra/terraform/modules/eks/main.tf
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "20.8.0"

  cluster_name    = "sk-${var.environment}"
  cluster_version = "1.29"
  vpc_id          = var.vpc_id
  subnet_ids      = var.private_subnet_ids

  eks_managed_node_groups = {
    general = {
      instance_types = var.environment == "production" ? ["m6i.xlarge"] : ["t3.medium"]
      min_size       = var.environment == "production" ? 3 : 1
      max_size       = var.environment == "production" ? 10 : 3
      desired_size   = var.environment == "production" ? 3 : 2
    }
    playwright = {  # High-memory nodes for checkout agents
      instance_types = ["m6i.2xlarge"]
      min_size       = 0
      max_size       = var.environment == "production" ? 20 : 2
      taints = [{ key = "workload", value = "playwright", effect = "NO_SCHEDULE" }]
      labels = { workload = "playwright" }
    }
  }

  cluster_addons = {
    coredns    = { most_recent = true }
    kube-proxy = { most_recent = true }
    vpc-cni    = { most_recent = true }
  }
}
```

### RDS Module

```hcl
# infra/terraform/modules/rds/main.tf
module "rds" {
  source  = "terraform-aws-modules/rds/aws"
  version = "6.5.0"

  identifier = "sk-${var.environment}"
  engine     = "postgres"
  engine_version = "16.2"
  family     = "postgres16"
  instance_class = var.environment == "production" ? "db.r6g.xlarge" : "db.t3.medium"

  allocated_storage     = var.environment == "production" ? 100 : 20
  max_allocated_storage = var.environment == "production" ? 500 : 50

  db_name  = "sahulatkar"
  username = "sk_admin"
  port     = 5432

  multi_az               = var.environment == "production"
  db_subnet_group_name   = var.database_subnet_group
  vpc_security_group_ids = [var.db_security_group_id]

  backup_retention_period = var.environment == "production" ? 35 : 7
  deletion_protection     = var.environment == "production"

  performance_insights_enabled = true
  create_db_parameter_group    = true

  parameters = [
    { name = "shared_preload_libraries", value = "pg_stat_statements,timescaledb" },
    { name = "log_min_duration_statement", value = "1000" },
    { name = "pgbouncer.pool_mode", value = "transaction" },
  ]
}

# Read replica (production only)
resource "aws_db_instance" "read_replica" {
  count               = var.environment == "production" ? 1 : 0
  identifier          = "sk-${var.environment}-read"
  replicate_source_db = module.rds.db_instance_identifier
  instance_class      = "db.r6g.large"
}
```

### ElastiCache Module

```hcl
# infra/terraform/modules/elasticache/main.tf
resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "sk-${var.environment}"
  description          = "SahulatKar Redis cluster"
  node_type            = var.environment == "production" ? "cache.r6g.large" : "cache.t3.medium"
  num_cache_clusters   = var.environment == "production" ? 3 : 1
  engine_version       = "7.2"
  port                 = 6379
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token           = var.redis_password
  subnet_group_name    = var.cache_subnet_group
  security_group_ids   = [var.redis_security_group_id]

  parameter_group_name = aws_elasticache_parameter_group.redis.name
}

resource "aws_elasticache_parameter_group" "redis" {
  name   = "sk-${var.environment}-redis7"
  family = "redis7"
  parameter { name = "maxmemory-policy"; value = "allkeys-lru" }
}
```

### ECR Module

```hcl
# infra/terraform/modules/ecr/main.tf
locals {
  services = ["gateway", "product-service", "credit-engine",
               "payment-orchestrator", "ledger-service",
               "notification-service", "web-customer", "web-admin"]
}

resource "aws_ecr_repository" "services" {
  for_each = toset(local.services)
  name     = "sk-${each.value}"
  image_scanning_configuration { scan_on_push = true }
  image_tag_mutability = "MUTABLE"
}

resource "aws_ecr_lifecycle_policy" "cleanup" {
  for_each   = aws_ecr_repository.services
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}
```

### S3 Module

```hcl
# infra/terraform/modules/s3/main.tf
locals {
  buckets = {
    contracts    = { versioning = true,  lifecycle_glacier = 365 }
    kyc_images   = { versioning = true,  lifecycle_glacier = 365 }
    screenshots  = { versioning = false, lifecycle_glacier = 90 }
    static       = { versioning = false, lifecycle_glacier = null }
  }
}

resource "aws_s3_bucket" "buckets" {
  for_each = local.buckets
  bucket   = "sk-${var.environment}-${each.key}"
  tags     = { Project = "SahulatKar", DataClass = "confidential" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "sse" {
  for_each = aws_s3_bucket.buckets
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_id
    }
  }
}
```

### Environment Composition

```hcl
# infra/terraform/environments/staging/main.tf
terraform {
  backend "s3" {
    bucket = "sk-terraform-state"
    key    = "staging/terraform.tfstate"
    region = "ap-south-1"
  }
}

module "vpc"         { source = "../../modules/vpc";         environment = "staging" }
module "ecr"         { source = "../../modules/ecr";         environment = "staging" }
module "rds"         { source = "../../modules/rds";         environment = "staging"; vpc_id = module.vpc.vpc_id; ... }
module "elasticache" { source = "../../modules/elasticache"; environment = "staging"; ... }
module "eks"         { source = "../../modules/eks";         environment = "staging"; vpc_id = module.vpc.vpc_id; ... }
module "s3"          { source = "../../modules/s3";          environment = "staging"; ... }
module "iam"         { source = "../../modules/iam";         environment = "staging"; ... }
module "kms"         { source = "../../modules/kms";         environment = "staging" }
```

---

## 8. CI/CD PIPELINE — PRODUCTION YAML

### Full CI Workflow

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: [main, develop, 'feature/**']
  pull_request:
    branches: [main, develop]

env:
  PYTHON_VERSION: "3.12"
  NODE_VERSION: "20"

jobs:
  # ─── DETECT CHANGES ───
  changes:
    runs-on: ubuntu-latest
    outputs:
      python_services: ${{ steps.filter.outputs.python_services }}
      frontend_apps: ${{ steps.filter.outputs.frontend_apps }}
      shared: ${{ steps.filter.outputs.shared }}
      infra: ${{ steps.filter.outputs.infra }}
      migrations: ${{ steps.filter.outputs.migrations }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            shared: 'packages/shared-python/**'
            migrations: 'db/migrations/**'
            infra: 'infra/**'
            gateway: 'apps/gateway/**'
            product-service: 'apps/product-service/**'
            credit-engine: 'apps/credit-engine/**'
            payment-orchestrator: 'apps/payment-orchestrator/**'
            ledger-service: 'apps/ledger-service/**'
            notification-service: 'apps/notification-service/**'
            web-customer: 'apps/web-customer/**'
            web-admin: 'apps/web-admin/**'

  # ─── PYTHON LINT ───
  python-lint:
    needs: changes
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [gateway, product-service, credit-engine, payment-orchestrator, ledger-service, notification-service]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ env.PYTHON_VERSION }}" }
      - run: pip install ruff mypy
      - run: ruff check apps/${{ matrix.service }}/src/
      - run: ruff check packages/shared-python/
      - run: mypy apps/${{ matrix.service }}/src/ --ignore-missing-imports

  # ─── PYTHON TESTS ───
  python-test:
    needs: python-lint
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [gateway, product-service, credit-engine, payment-orchestrator, ledger-service, notification-service]
    services:
      postgres:
        image: timescale/timescaledb:2.14.2-pg16
        env:
          POSTGRES_DB: sahulatkar_test
          POSTGRES_USER: sk_test
          POSTGRES_PASSWORD: testpass
        ports: ["5432:5432"]
        options: --health-cmd pg_isready --health-interval 5s --health-retries 5
      redis:
        image: redis:7.2-alpine
        ports: ["6379:6379"]
        options: --health-cmd "redis-cli ping" --health-interval 5s --health-retries 5
    env:
      DATABASE_URL: postgresql+asyncpg://sk_test:testpass@localhost:5432/sahulatkar_test
      REDIS_URL: redis://localhost:6379/0
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ env.PYTHON_VERSION }}" }
      - run: pip install -e "packages/shared-python[test]"
      - run: pip install -e "apps/${{ matrix.service }}[test]"
      - run: alembic -c db/migrations/alembic.ini upgrade head
      - run: pytest apps/${{ matrix.service }}/tests/ -v --cov=apps/${{ matrix.service }}/src --cov-fail-under=80 --junitxml=test-results.xml
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: "test-results-${{ matrix.service }}", path: test-results.xml }

  # ─── FRONTEND ───
  frontend-test:
    needs: changes
    runs-on: ubuntu-latest
    strategy:
      matrix:
        app: [web-customer, web-admin]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "${{ env.NODE_VERSION }}" }
      - run: cd apps/${{ matrix.app }} && npm ci
      - run: cd apps/${{ matrix.app }} && npm run lint
      - run: cd apps/${{ matrix.app }} && npx tsc --noEmit
      - run: cd apps/${{ matrix.app }} && npm test -- --coverage --passWithNoTests

  # ─── MIGRATION CHECK ───
  migration-check:
    needs: python-lint
    runs-on: ubuntu-latest
    services:
      postgres:
        image: timescale/timescaledb:2.14.2-pg16
        env: { POSTGRES_DB: sahulatkar_test, POSTGRES_USER: sk_test, POSTGRES_PASSWORD: testpass }
        ports: ["5432:5432"]
        options: --health-cmd pg_isready --health-interval 5s --health-retries 5
    env:
      DATABASE_URL: postgresql+asyncpg://sk_test:testpass@localhost:5432/sahulatkar_test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ env.PYTHON_VERSION }}" }
      - run: pip install alembic asyncpg sqlalchemy psycopg2-binary
      - run: pip install -e packages/shared-python
      - run: alembic -c db/migrations/alembic.ini upgrade head
      - run: alembic -c db/migrations/alembic.ini downgrade -1
      - run: alembic -c db/migrations/alembic.ini upgrade head

  # ─── HARD GATE (NEVER SKIP) ───
  hard-gate:
    needs: python-test
    runs-on: ubuntu-latest
    services:
      postgres:
        image: timescale/timescaledb:2.14.2-pg16
        env: { POSTGRES_DB: sahulatkar_test, POSTGRES_USER: sk_test, POSTGRES_PASSWORD: testpass }
        ports: ["5432:5432"]
      redis:
        image: redis:7.2-alpine
        ports: ["6379:6379"]
    env:
      DATABASE_URL: postgresql+asyncpg://sk_test:testpass@localhost:5432/sahulatkar_test
      REDIS_URL: redis://localhost:6379/0
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ env.PYTHON_VERSION }}" }
      - run: pip install -e "packages/shared-python[test]" && pip install -e "apps/gateway[test]"
      - run: pytest apps/gateway/tests/test_hard_gate.py -v --tb=short

  # ─── DOCKER BUILD VERIFY ───
  docker-build:
    needs: [python-test, frontend-test]
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [gateway, product-service, credit-engine, payment-orchestrator, ledger-service, notification-service, web-customer, web-admin]
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - run: docker build -f apps/${{ matrix.service }}/Dockerfile -t sk-${{ matrix.service }}:ci .

  # ─── TERRAFORM VALIDATE ───
  terraform-validate:
    needs: changes
    if: needs.changes.outputs.infra == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - run: cd infra/terraform/environments/staging && terraform init -backend=false && terraform validate
      - run: terraform fmt -check -recursive infra/terraform/
```

### Full CD Workflow

```yaml
# .github/workflows/build-and-push.yml
name: Build & Deploy
on:
  push:
    branches: [main]

env:
  AWS_REGION: ap-south-1
  ECR_REGISTRY: ${{ secrets.ECR_REGISTRY }}

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      services: ${{ steps.set.outputs.services }}
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 2 }
      - id: set
        run: |
          CHANGED=$(git diff --name-only HEAD~1 HEAD | grep '^apps/' | cut -d'/' -f2 | sort -u | jq -R . | jq -s .)
          echo "services=$CHANGED" >> $GITHUB_OUTPUT

  build-push:
    needs: detect-changes
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: ${{ fromJson(needs.detect-changes.outputs.services) }}
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}
      - uses: aws-actions/amazon-ecr-login@v2
      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v5
        with:
          context: .
          file: apps/${{ matrix.service }}/Dockerfile
          push: true
          tags: |
            ${{ env.ECR_REGISTRY }}/sk-${{ matrix.service }}:${{ github.sha }}
            ${{ env.ECR_REGISTRY }}/sk-${{ matrix.service }}:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy-staging:
    needs: build-push
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}
      - run: aws eks update-kubeconfig --name sk-staging --region ${{ env.AWS_REGION }}
      - run: |
          cd infra/k8s/overlays/staging
          kustomize edit set image ${ECR_REGISTRY}/sk-*:${GITHUB_SHA}
          kustomize build . | kubectl apply -f -
      - run: |
          for svc in gateway product-service credit-engine payment-orchestrator ledger-service notification-service; do
            kubectl rollout status deployment/sk-$svc -n sahulatkar --timeout=300s
          done

  smoke-test:
    needs: deploy-staging
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          curl -sf https://staging-api.sahulatkar.com/health | jq .
          curl -sf https://staging-api.sahulatkar.com/credit/me | jq .

  deploy-production:
    needs: smoke-test
    runs-on: ubuntu-latest
    environment: production  # Requires manual approval in GitHub
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_PROD_DEPLOY_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}
      - run: aws eks update-kubeconfig --name sk-production --region ${{ env.AWS_REGION }}
      - run: |
          cd infra/k8s/overlays/production
          kustomize edit set image ${ECR_REGISTRY}/sk-*:${GITHUB_SHA}
          kustomize build . | kubectl apply -f -
      - run: |
          for svc in gateway product-service credit-engine payment-orchestrator ledger-service notification-service; do
            kubectl rollout status deployment/sk-$svc -n sahulatkar --timeout=300s
          done
```

---

## 9. FRONTEND PAGE BREAKDOWN

### Customer App (`apps/web-customer/`) — 20 Screens

| Screen | Route | Components | API Calls |
|---|---|---|---|
| US-01 Splash | `/` | Logo animation, CTA | None |
| US-02 Register | `/auth/register` | PhoneInput, Button | POST /auth/register/initiate |
| US-03 OTP Verify | `/auth/verify` | OTPInput (6-digit) | POST /auth/verify-otp |
| US-04 CNIC Front | `/kyc/cnic-front` | CameraCapture, CropOverlay | POST /kyc/start, S3 upload |
| US-05 CNIC Back | `/kyc/cnic-back` | CameraCapture | POST /kyc/verify-cnic |
| US-06 Liveness | `/kyc/liveness` | LivenessSDK (Shufti) | POST /kyc/verify-liveness |
| US-07 Processing | `/kyc/processing` | AnimatedLoader, StatusCard | GET /kyc/status (poll 3s) |
| US-08 Credit Reveal | `/credit/reveal` | CreditBand animation | GET /auth/me |
| US-09 Home | `/home` | URLPasteInput, OrderList | GET /orders |
| US-10 Extracting | `/order/{id}/extracting` | StepProgress, Skeleton | GET /products/jobs/{id} (poll 3s) |
| US-11 Product Preview | `/order/{id}/offer` | ProductCard, PlanSelector | GET /products/{id}/offer |
| US-12 Wakalah Sign | `/order/{id}/wakalah` | ContractViewer, OTPInput | POST /contracts/wakalah/sign |
| US-13 Murabaha Sign | `/order/{id}/murabaha` | ContractViewer, DisclosureTable, OTPInput | POST /contracts/murabaha/sign |
| US-14 Down Payment | `/order/{id}/pay` | PaymentMethodSelector, AmountDisplay | POST /payments/down-payment |
| US-15 Agent Executing | `/order/{id}/purchasing` | SSE progress, StepList | GET /agent/job/{id}/status (SSE) |
| US-16 Purchase Complete | `/order/{id}/confirmed` | ConfirmationCard, ReceiptLink | GET /orders/{id} |
| US-17 Order Tracking | `/order/{id}/tracking` | TrackingTimeline, MapView | GET /tracking/{id} |
| US-18 Wallet | `/wallet` | BalanceCard, TransactionList | GET /payments/schedule |
| US-19 Pay Installment | `/wallet/pay/{id}` | PaymentMethodSelector | POST /payments/pay-installment |
| US-20 Profile | `/profile` | UserInfo, CreditInfo, Settings | GET /auth/me, GET /credit/me |

### Shared Components Library

```
apps/web-customer/src/components/
├── ui/                    # Atomic: Button, Input, Card, Badge, Modal, Toast
├── forms/                 # PhoneInput, OTPInput, URLPasteInput
├── layout/                # Navbar, BottomNav, PageWrapper, LoadingScreen
├── credit/                # CreditBand, CreditMeter, LimitCard
├── payment/               # PaymentMethodSelector, InstallmentCard, PlanSelector
├── product/               # ProductCard, PriceBreakdown, VariantSelector
├── contracts/             # ContractViewer, DisclosureTable, SignatureConfirm
├── tracking/              # TrackingTimeline, StatusBadge
└── icons/                 # Custom SVG icons
```

### Admin App (`apps/web-admin/`) — 28 Screens

Covered by module specs AD-01 through AD-28 in `System-md-files/M10-M12-delivery-ledger-admin.md`.

Key admin components:
```
apps/web-admin/src/components/
├── dashboard/   # KPICard, TrendChart, DonutChart, FunnelChart
├── tables/      # DataTable (sortable, filterable, paginated), ExportButton
├── forms/       # SearchBar, DateRangePicker, FilterPanel, InlineEdit
├── layout/      # Sidebar, TopBar, Breadcrumbs, TabNav
├── modals/      # ConfirmDialog, DetailDrawer, UserProfileDrawer
├── charts/      # LineChart, BarChart, CohortGrid (Recharts or Chart.js)
└── queue/       # QueueItem, ClaimButton, PriorityBadge, SLACountdown
```

---

## 10. DEPLOYMENT RUNBOOK

### First-Time Setup (One-time)

```bash
# 1. Terraform init + apply (staging first)
cd infra/terraform/environments/staging
terraform init
terraform plan -out=staging.plan
terraform apply staging.plan

# 2. Configure kubectl
aws eks update-kubeconfig --name sk-staging --region ap-south-1

# 3. Create namespace
kubectl create namespace sahulatkar

# 4. Install addons
helm install ingress-nginx ingress-nginx/ingress-nginx -n ingress-nginx --create-namespace
helm install cert-manager jetstack/cert-manager -n cert-manager --create-namespace --set installCRDs=true
helm install keda kedacore/keda -n keda --create-namespace
helm install prometheus prometheus-community/kube-prometheus-stack -n monitoring --create-namespace

# 5. Create secrets
kubectl create secret generic sk-gateway-secrets -n sahulatkar --from-env-file=.env.staging
# ... repeat for each service

# 6. Run migrations
kubectl run migrations --rm -it --image=${ECR}/sk-gateway:latest -n sahulatkar \
  --env="DATABASE_URL=..." -- alembic -c db/migrations/alembic.ini upgrade head

# 7. Deploy
kustomize build infra/k8s/overlays/staging | kubectl apply -f -

# 8. Verify
kubectl get pods -n sahulatkar
curl https://staging-api.sahulatkar.com/health
```

### Routine Deployment (per release)

```bash
# CI/CD handles this automatically on merge to main
# Manual override if needed:
git tag v1.X.Y && git push origin v1.X.Y
# → Triggers build-and-push.yml → staging → smoke → production (manual gate)
```

---

## 11. ROLLBACK PROCEDURES

### Application Rollback

```bash
# Option 1: Revert to previous image tag
kubectl set image deployment/sk-gateway app=${ECR}/sk-gateway:${PREVIOUS_SHA} -n sahulatkar
kubectl rollout status deployment/sk-gateway -n sahulatkar

# Option 2: Undo last rollout
kubectl rollout undo deployment/sk-gateway -n sahulatkar

# Option 3: Revert Git commit and re-deploy
git revert HEAD && git push origin main
# → CD pipeline deploys reverted code
```

### Database Rollback

```bash
# Downgrade one migration
kubectl run migration-rollback --rm -it --image=${ECR}/sk-gateway:latest -n sahulatkar \
  --env="DATABASE_URL=..." -- alembic -c db/migrations/alembic.ini downgrade -1
```

### Infrastructure Rollback

```bash
# Terraform state rollback
cd infra/terraform/environments/staging
terraform plan -target=module.rds  # Review changes
terraform apply -target=module.rds
```

---

## 12. DATA SEEDING STRATEGY

### Seed Script Location: `scripts/seed_data.py`

```python
# Migration 016_seed_data.py covers:

# 1. RBAC Roles & Permissions
ROLES = ['super_admin', 'operations_manager', 'credit_risk_analyst',
         'fraud_analyst', 'cs_agent', 'finance_analyst',
         'compliance_officer', 'marketing_manager']

# 2. Prohibited Categories (Shariah Rule 3)
PROHIBITED = ['Alcohol', 'Tobacco', 'Gambling', 'Adult Content',
              'Weapons', 'Interest-bearing instruments', 'Non-halal food']

# 3. Ledger Chart of Accounts
ACCOUNTS = [
    ('1001', 'Cash/Bank', 'asset'),
    ('1100', 'AR-Installments', 'asset'),
    ('1200', 'VCNs Issued', 'asset'),
    ('2001', 'AP-Merchants', 'liability'),
    ('2100', 'Charity Payable', 'liability'),
    ('4001', 'Murabaha Profit', 'revenue'),
    ('5001', 'COGS-Merchant Payment', 'expense'),
    # ... full list in M11 spec
]

# 4. Courier Registry
COURIERS = [
    ('TCS', 'tcs', 'tcs-express', ['Punjab', 'Sindh', 'KPK', 'Islamabad']),
    ('Leopards', 'leo', 'leopards-courier', ['Punjab', 'Sindh', 'KPK']),
    ('M&P', 'mnp', 'muller-and-phipps', ['Punjab', 'Sindh']),
    ('PostEx', 'postex', 'postex', ['Punjab', 'Sindh', 'KPK']),
]

# 5. Fraud Rules (initial set)
FRAUD_RULES = [
    ('VEL_ORDERS_24H', 'Orders per 24h', {'entity': 'user', 'window': '24h'}, 3, 'block'),
    ('VEL_ORDERS_1H', 'Orders per 1h', {'entity': 'user', 'window': '1h'}, 1, 'review'),
    # ... full list in M04 spec
]

# 6. System Settings
SETTINGS = [
    ('credit.auto_approve_threshold', '700'),
    ('credit.manual_review_range_low', '600'),
    ('credit.first_time_limit', '25000'),
    ('credit.max_limit', '500000'),
    ('murabaha.markup_pay_in_3', '0.025'),
    ('murabaha.markup_pay_in_4', '0.040'),
    ('murabaha.markup_pay_in_6', '0.070'),
]

# 7. Feature Flags (all off by default)
FLAGS = ['jazzcash_enabled', 'raast_enabled', 'lithic_vcn',
         'playwright_checkout', 'hitl_queue', 'tasdeeq_reporting']
```

---

## 13. API VERSIONING STRATEGY

```
# URL-based versioning: /api/v1/...
# Gateway routes all /api/v1/* to internal services

# Each service handles its own versioned router:
api/
├── __init__.py
├── routes.py          # Aggregates all version routers
└── v1/
    ├── __init__.py
    ├── auth.py
    ├── kyc.py
    └── ...

# In routes.py:
from src.api.v1 import auth, kyc
router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(kyc.router)
```

---

## 14. ERROR CODE REGISTRY

### Standard Error Response

```json
{
  "error": {
    "code": "MURABAHA_NOT_SIGNED",
    "message": "Murabaha contract must be signed before VCN issuance",
    "details": {},
    "request_id": "uuid"
  }
}
```

### Error Codes By Domain

| Domain | Code | HTTP | Description |
|---|---|---|---|
| Auth | PHONE_ALREADY_REGISTERED | 409 | Duplicate phone |
| Auth | INVALID_PHONE_FORMAT | 422 | Not E.164 |
| Auth | INVALID_OTP | 400 | Wrong OTP code |
| Auth | OTP_EXPIRED | 400 | OTP TTL exceeded |
| Auth | TOO_MANY_ATTEMPTS | 429 | Rate limited |
| KYC | CNIC_BLOCKED | 422 | NADRA blocked |
| KYC | CNIC_EXPIRED | 422 | NADRA expired |
| KYC | LIVENESS_FAILED | 422 | Anti-spoof fail |
| KYC | FACE_MISMATCH | 422 | < 70% match |
| Product | NOT_A_PRODUCT_URL | 422 | Not product page |
| Product | PROHIBITED_CATEGORY | 422 | Shariah blocked |
| Product | OUT_OF_STOCK | 422 | Unavailable |
| Credit | CREDIT_DECLINED | 403 | Score < threshold |
| Credit | INSUFFICIENT_CREDIT | 403 | Limit exceeded |
| Contract | MURABAHA_NOT_SIGNED | 403 | Hard gate |
| Contract | ALREADY_SIGNED | 409 | Duplicate sign |
| Contract | CONFIRMATION_REQUIRED | 400 | Missing checkbox |
| Payment | PAYMENT_FAILED | 402 | Gateway declined |
| Payment | DUPLICATE_PAYMENT | 409 | Idempotency hit |
| VCN | VCN_ISSUANCE_FAILED | 502 | Stripe error |
| Agent | CHECKOUT_FAILED | 502 | All retries exhausted |
| System | SERVICE_UNAVAILABLE | 503 | Dependency down |
| System | RATE_LIMITED | 429 | Request throttled |

---

## 15. PERFORMANCE BUDGETS

### API Latency Targets (p99)

| Endpoint | Target | Hard Limit |
|---|---|---|
| GET /health | < 10ms | 50ms |
| POST /auth/register/initiate | < 200ms | 500ms |
| POST /auth/verify-otp | < 100ms | 300ms |
| GET /credit/check | < 3s | 5s |
| POST /products/extract (Tier 1-2) | < 5s | 10s |
| POST /products/extract (Tier 3) | < 60s | 120s |
| POST /payments/down-payment | < 2s | 5s |
| POST /vcn/issue | < 3s | 5s |
| GET /admin/dashboard | < 500ms | 1s |

### Frontend Performance

| Metric | Target |
|---|---|
| First Contentful Paint | < 1.5s |
| Largest Contentful Paint | < 2.5s |
| Cumulative Layout Shift | < 0.1 |
| First Input Delay | < 100ms |
| Total Bundle Size (gzipped) | < 300KB |
| Lighthouse Score | > 90 |

### Database Performance

| Query | Target | Index |
|---|---|---|
| User lookup by phone | < 1ms | `users(phone)` |
| Credit check (full pipeline) | < 500ms | Composite on risk_assessments |
| Installment due today | < 50ms | `installments(due_date, user_id) WHERE status='pending'` |
| Webhook lookup by txn_id | < 1ms | Hash index on `payment_transactions(gateway_txn_id)` |
| Order by user (last 10) | < 5ms | `orders(user_id, created_at DESC)` |
| Audit trail by entity | < 10ms | `audit_trails(entity_type, entity_id, created_at)` |

---

## HOW TO USE BOTH PLAN FILES

When starting a new AI chat session, paste:

```
"I'm working on the SahulatKar BNPL platform.
Please read these two files for full context:
- MASTER_PLAN.md (system overview, phases, sprint file lists, CI/CD, checklists)
- MASTER_PLAN_DETAILED.md (inter-service contracts, DB schema, K8s, Terraform, frontend)
Also read the relevant module spec from System-md-files/M0X-*.md

Current task: [SPRINT] [ITERATION] — [DESCRIPTION]
Example: Sprint S01 Iteration 1A — Shared Python package hardening"
```

---

## 16. IN-DEPTH E2E INTEGRATION TESTING FRAMEWORK

To ensure correct 12-step flow execution across the 6 microservices, a dedicated E2E test suite using **Playwright** and **pytest-asyncio** is required for Phase 4.

### The 12-Step Simulator
The simulator must automate the entire user transaction path:
1. **Mock Gateway Input**: Submit URL via `POST /gateway/products/extract`.
2. **Polling API**: Poll product extracting status. VLM/Playwright scraping is mocked if testing locally without BrightData, but full run on test environment.
3. **Credit Engine Trigger**: Initiate credit check, assert 7-layer scoring calculates an approval.
4. **Contract Signatures**: Automate 2 OTP completions (Wakalah & Murabaha).
5. **Down Payment**: Intercept test Safepay webhook and trigger down-payment success.
6. **VCN Assertion**: Check `payment-orchestrator` issues logical test Stripe card.
7. **Purchase Automation (Playwright)**: Checkout worker fires up headless browser. Assert state reaches `Purchase Complete`.
8. **Delivery Webhook**: Simulate AfterShip delivery webhook hitting notification-service.
9. **Ledger Assertion**: Ensure `ledger-service` activates remaining installments via double-entry.

### Testing Gaps to Resolve
- **Idempotency Flakiness**: Ensure duplicate webhook fires don't duplicate ledger accounts. Need specific tests testing network retry spamming on Safepay/JazzCash.
- **Agent Self-Healing Tests**: Need to mock a checkout selector failure and ensure the GPT-4o fallback recovery script executes correctly.
- **Rollback Flows**: Ensure canceled Murabaha contracts properly reverse the entire double-entry ledger back to zero balance.
