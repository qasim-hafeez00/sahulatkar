# Infrastructure Architecture

**Status:** STABLE (design/provisioning) — per `docs/MASTER_PLAN.md`'s current-state table, Terraform and K8s manifests are marked "Done"/fully provisioned; operational maturity gaps (observability, secret rotation) flagged below.

## Cloud & region

AWS, region `ap-south-1` — chosen specifically for data-residency reasons (Pakistan-adjacent, cited against a PECA 2016 requirement; see [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md)). All data is committed to stay within this region.

## Compute

EKS (Kubernetes), with KEDA for queue-depth-driven autoscaling — notably the checkout-agent pods, which scale 0→100 based on the Playwright job queue length rather than CPU/memory alone.

## Terraform module layout

```
infra/terraform/
├── modules/
│   ├── vpc/          — VPC, subnets, NAT, security groups
│   ├── eks/          — EKS cluster, node groups, IRSA
│   ├── rds/          — PostgreSQL 16, read replica, parameter groups
│   ├── elasticache/  — Redis 7, 3-node cluster
│   ├── ecr/           — 8 repositories (one per service)
│   ├── s3/            — Buckets: contracts, KYC images, screenshots, static
│   ├── iam/            — Service roles, policies, OIDC
│   ├── kms/            — Encryption keys for PII
│   └── pgbouncer/      — ECS task for PgBouncer
└── environments/
    ├── staging/    — smaller instances, single AZ
    └── production/ — multi-AZ, r6g.xlarge, 3-node Redis
```

## Kubernetes manifest layout (Kustomize)

```
infra/k8s/
├── base/{service}/       — deployment (2 replicas), service (ClusterIP), HPA (min 2, max 10, CPU 70%)
├── base/pgbouncer/
├── keda/                 — scaled-objects.yaml (checkout agent 0→100 on queue length)
└── overlays/
    ├── staging/          — 1 replica, smaller resources
    └── production/       — 2+ replicas, full resources, PodDisruptionBudget
```

## Environments

| Env | Purpose | DB | URL |
|---|---|---|---|
| local | Development | docker-compose PostgreSQL | `localhost:8000` |
| test | CI automated tests | testcontainers PostgreSQL | N/A |
| staging | Pre-production | RDS staging | `staging-api.sahulatkar.com` |
| production | Live | RDS production | `api.sahulatkar.com` |

## Secret management

Local: `.env` (gitignored). CI: GitHub Actions secrets. Staging/production: AWS Secrets Manager → Kubernetes ExternalSecrets (see `docs/SECRETS_MANAGER_MIGRATION.md`). **Known gap:** no rotation mechanism exists yet (`INF-GAP-07`).

## Known infrastructure gaps (from `docs/PRODUCTION_GAPS_REPORT.md` §11)

- **No observability stack running:** Prometheus `/metrics` endpoints exist per-service, but no Grafana dashboards, no alerting rules (`INF-GAP-01`).
- **No log aggregation:** logs stay on pods and are lost on restart — no Fluent Bit/OpenSearch/Loki pipeline configured (`INF-GAP-02`).
- **No distributed tracing:** OpenTelemetry referenced in Product Service but not verified platform-wide; no Jaeger/Tempo collector configured (`INF-GAP-03`).
- **`X-Request-ID` not propagated downstream:** generated at Gateway but not forwarded to the other 5 services, so a single order cannot currently be traced across the full pipeline (`INF-GAP-04`).
- **Migrations not automated on deploy:** no `alembic upgrade head` step in the K8s deployment manifest — a manual step is currently required (`INF-GAP-11`).
- **Windows-only dev tooling:** `start_all.ps1` has no cross-platform (Makefile/shell) equivalent (`INF-GAP-12`, low severity but a real onboarding friction point for non-Windows contributors).

## Related documents

[`34-deployment-process.md`](34-deployment-process.md), [`35-monitoring-logging.md`](35-monitoring-logging.md), [`../05-architecture/20-system-architecture.md`](../05-architecture/20-system-architecture.md).
