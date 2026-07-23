# Monitoring (Prometheus + Grafana + Alertmanager)

Self-hosted, in-cluster `kube-prometheus-stack` (per the user's decision — not
AWS-managed AMP/AMG). Installed **once per EKS cluster** — staging and
production are separate clusters (`infra/terraform/environments/staging` and
`.../production` each provision their own `module "eks"`), so this is run
twice against two different `kubectl` contexts, not once with two overlays.

## What was verified before writing any scrape config

The plan this implements assumes "every service already emits Prometheus
metrics." That was checked against the actual source, not taken on faith:

| Service | Metrics? | Path | Port | Pod annotations already present? |
|---|---|---|---|---|
| gateway | yes (`prometheus_fastapi_instrumentator`) | `/api/v1/metrics` | 8000 | yes, but **path was wrong** (said `/metrics`) — fixed in `infra/k8s/base/gateway/deployment.yaml` as part of this change |
| product-service | yes (hand-rolled `prometheus_client` middleware) | `/metrics` | 8000 | yes, correct |
| payment-orchestrator | yes (hand-rolled) | `/metrics` | 8000 | yes, correct |
| ledger-service | yes (hand-rolled) | `/metrics` | 8000 | yes, correct |
| notification-service | yes (`make_asgi_app()` mounted) | `/metrics` | 8000 | yes, correct |
| credit-engine | **no** — annotations exist but there is no `prometheus_client`/instrumentator usage anywhere in `apps/credit-engine/src` | n/a | n/a | annotations present but currently point at a route that doesn't exist. Not fixed here (credit-engine is explicitly out of scope for this track) — it will just show up as a failing scrape target until credit-engine adds instrumentation. |
| web-admin, web-customer | no | — | — | none present, correctly not annotated |
| pgbouncer | no (no exporter sidecar configured) | — | — | none present |

So the plan's "every service already emits metrics" claim is **mostly true
but not uniform**: five backend services genuinely expose Prometheus
metrics, credit-engine's annotation is aspirational/unwired, and the two
frontends + pgbouncer never claimed to.

The five real services also do **not** share one metric schema — see
`alert-rules.yaml` and `grafana-dashboard-golden-signals.yaml` for the exact
per-service metric names/labels used (nothing below is invented):

- `gateway`: `http_requests_total{method,status,handler}`,
  `http_request_duration_seconds{method,handler}` (instrumentator defaults)
- `product-service`: `http_requests_total{method,endpoint,status_code}` —
  same metric **name** as gateway, different label **names**
  (`status_code`/`endpoint` vs `status`/`handler`)
- `ledger-service`: `ledger_http_requests_total{method,path,status_code}`
- `notification-service`:
  `notification_http_requests_total{method,endpoint,status_code}`
- `payment-orchestrator`: **no generic request-count/status-code metric at
  all** — only `payment_request_latency_seconds` (latency, unlabeled by
  status). Its alert rule and dashboard panel use
  `payment_gateway_failure_total` as the closest proxy instead of a
  fabricated error-rate metric.

## Why annotation-based scraping instead of ServiceMonitors

The deployments already carry `prometheus.io/scrape` / `prometheus.io/port`
/ `prometheus.io/path` pod annotations (someone wired that in before this
track). Rather than duplicate that same information into 5 near-identical
`ServiceMonitor` CRs, `prometheus-values.yaml` adds one
`additionalScrapeConfigs` job that reproduces the classic annotation-based
Kubernetes SD discovery job, so the existing annotations just start being
consumed. `ruleSelectorNilUsesHelmValues` / `serviceMonitorSelectorNilUsesHelmValues`
/ `podMonitorSelectorNilUsesHelmValues` are all set to `false` so a future
`ServiceMonitor` (e.g. for an ingress controller) is still picked up
automatically if anyone adds one later.

## Files

- `namespace.yaml` — the `monitoring` namespace.
- `prometheus-values.yaml` — Helm values for `kube-prometheus-stack`
  (Prometheus, Grafana, Alertmanager, node-exporter, kube-state-metrics).
  Disables etcd/scheduler/controller-manager/kube-proxy scraping (not
  reachable on EKS — the managed control plane isn't exposed to the
  cluster, so leaving these on just produces permanently-down targets).
- `alert-rules.yaml` — a `PrometheusRule` CRD: pod crash-looping, per-service
  high-error-rate (4 of 5 backend services — see the payment-orchestrator
  gap above), and cluster-wide container memory/CPU-vs-limit pressure.
  Thresholds are derived from the resource requests/limits already set per
  service in `infra/k8s/base/*/deployment.yaml` and the 70%/80% CPU/memory
  HPA targets already set in `infra/k8s/base/*/hpa.yaml` — not invented
  numbers.
- `grafana-dashboard-golden-signals.yaml` — a `ConfigMap` (labeled
  `grafana_dashboard: "1"`) holding one starter dashboard: request
  rate/error rate/p95 latency per service (using each service's real
  metric names), pod restarts, and memory/CPU-vs-limit.

## Why this isn't wired into the app Kustomize tree

`infra/k8s/base/kustomization.yaml` is consumed by both
`infra/k8s/overlays/staging` and `.../production`, each of which applies a
blanket `namespace: sk-staging` / `namespace: sk-production` transform to
every resource it produces. Folding `monitoring/` into that tree would mean:

1. The cluster-wide monitoring stack gets forced into an app-specific
   namespace (`sk-staging`) instead of its own `monitoring` namespace.
2. It becomes tied to the app release cadence/replica-count patches
   (`overlays/staging/hpa-min-replicas-patch.yaml` etc.) that have nothing
   to do with it.

So `monitoring/` (and `logging/`) are standalone Kustomize roots, applied
directly and independently of the app tree — this is the "Helm and Kustomize
coexisting without one wrapping the other" pattern.

## Install order

Run once per cluster (staging cluster, then production cluster, with
`kubectl config use-context` pointed at each in turn):

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# 1. Install the chart (creates CRDs: ServiceMonitor, PodMonitor, PrometheusRule, Alertmanager, Prometheus)
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f infra/k8s/base/monitoring/prometheus-values.yaml

# 2. Apply the raw manifests that build on top of it (namespace is idempotent,
#    PrometheusRule/dashboard ConfigMap need the CRDs from step 1 to exist first)
kubectl apply -k infra/k8s/base/monitoring

# Upgrades later:
helm upgrade kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  -f infra/k8s/base/monitoring/prometheus-values.yaml
```

Grafana's admin password is auto-generated into a `Secret` by the chart
unless overridden — do not hardcode one into `prometheus-values.yaml`.
Retrieve it with:

```bash
kubectl -n monitoring get secret kube-prometheus-stack-grafana \
  -o jsonpath="{.data.admin-password}" | base64 -d
```

## Validation performed

Neither `helm` nor a live cluster were available in this environment.
`kubectl` (v1.32.2, with Kustomize v5.5.0 built in) is available, so:

- `kubectl kustomize infra/k8s/base/monitoring` was run to confirm the raw
  manifests (namespace, `PrometheusRule`, dashboard `ConfigMap`) parse and
  build correctly. This does **not** validate the `PrometheusRule`/CRD
  schema itself (that requires the CRDs to be installed, which needs
  `helm`) — the PromQL expressions and YAML structure were hand-checked
  against the `monitoring.coreos.com/v1` `PrometheusRule` spec instead.
- `prometheus-values.yaml` / `../logging/loki-values.yaml` /
  `../logging/fluent-bit-values.yaml` could not be checked with
  `helm template` (no `helm` binary in this environment) — they were
  hand-verified for YAML syntax and cross-checked field names against each
  chart's documented schema from memory. **Before the first real install,
  run `helm template` against these values files in an environment with
  `helm` and fix any drift from the exact chart versions you pin.**
