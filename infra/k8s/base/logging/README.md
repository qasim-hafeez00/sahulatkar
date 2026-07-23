# Centralized log aggregation (Fluent Bit -> Loki)

Self-hosted, in-cluster Loki (single-binary mode) + Fluent Bit DaemonSet,
installed once per EKS cluster (staging and production are separate
clusters — see `../monitoring/README.md` for why that matters here too).

## What was verified before writing the collector config

All five instrumented backend services (`gateway`, `product-service`,
`payment-orchestrator`, `ledger-service`, `notification-service`) log to
stdout, which is what Fluent Bit's DaemonSet tails via
`/var/log/containers/*.log` on every node — no app-side change needed for
basic collection. But their logging setups are **not uniform**, which
changes what actually lands as structured data in Loki vs. as an opaque
text line (verified by reading each service's logging setup, not assumed):

| Service | Setup | Result |
|---|---|---|
| `gateway` (`src/core/logging.py`) | `pythonjsonlogger.JsonFormatter` on the root logger | genuine single-JSON-object log lines |
| `payment-orchestrator` (`src/core/logging.py`) | `pythonjsonlogger.jsonlogger.JsonFormatter`, fields renamed to `timestamp`/`level`/`logger`, plus a static `service` field | genuine single-JSON-object log lines |
| `ledger-service` (`src/core/logging.py`) | `logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s")` — plain text, not JSON | plain text; the `extra={...}` fields its middleware attaches (`request_id`, `status_code`, `duration_ms`, ...) are **not rendered** by this formatter |
| `notification-service` (`src/core/logging.py`) | `logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')` — plain text | plain text |
| `product-service` (`src/middleware/logging.py`) | no root JSON formatter; middleware manually does `logger.info(json.dumps(log_record))` | the JSON is a *substring* of an otherwise plain-text line, not the whole line |

`fluent-bit-values.yaml`'s JSON parser step uses `Reserve_Data On`, so this
is handled gracefully rather than assumed away: gateway and
payment-orchestrator get real structured-field extraction in Loki; the
other three fail the JSON parse and ship as unparsed raw text (still fully
searchable by `namespace`/`pod`/`container` label and full-text query in
Loki, just not field-structured). Making the other three consistent with
gateway's formatter is an app-code change, out of scope for this infra
track.

## Fluent Bit vs. Promtail

Chose **Fluent Bit**:

1. The plan itself names it explicitly: "Fluent Bit -> Loki or CloudWatch
   Logs."
2. It's a small C binary (~450KB) with meaningfully lower per-node memory
   than Promtail's Go runtime — relevant since this runs as a DaemonSet on
   every node in the cluster, not a single instance.
3. It ships first-class output plugins for **both** Loki and CloudWatch
   Logs. Promtail only speaks Loki. Given the plan explicitly floats
   "Loki or CloudWatch Logs" as open destinations, picking the collector
   that can point at either without being swapped out later is the safer
   default — a future move to CloudWatch Logs is a values-file `[OUTPUT]`
   block edit, not a different DaemonSet.

## Files

- `namespace.yaml` — the `logging` namespace.
- `loki-values.yaml` — Helm values for `grafana/loki`, `SingleBinary`
  deployment mode (not the SimpleScalable/Distributed microservices
  topology — this scale, one small-to-mid cluster per environment, doesn't
  need it). Filesystem-backed PVC storage, 7-day retention to keep the
  footprint small; revisit with the existing
  `infra/terraform/modules/s3` module if longer retention is needed later.
- `fluent-bit-values.yaml` — Helm values for `fluent/fluent-bit` as a
  DaemonSet: tails container logs, enriches with Kubernetes pod metadata,
  opportunistically parses JSON (see table above), ships to
  `loki.logging.svc.cluster.local:3100`.

## Why this isn't wired into the app Kustomize tree

Same reasoning as `../monitoring/README.md` — a cluster-wide DaemonSet
add-on shouldn't be forced into `sk-staging`/`sk-production` by the app
overlays' blanket namespace transform, and shouldn't be coupled to the app
release cadence. `logging/` is a standalone Kustomize root, applied
directly.

## Install order

Run once per cluster:

```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# 1. Namespace + Loki
kubectl apply -k infra/k8s/base/logging
helm install loki grafana/loki \
  --namespace logging \
  -f infra/k8s/base/logging/loki-values.yaml

# 2. Fluent Bit DaemonSet (after Loki is up, so the [OUTPUT] host resolves)
helm repo add fluent https://fluent.github.io/helm-charts
helm repo update
helm install fluent-bit fluent/fluent-bit \
  --namespace logging \
  -f infra/k8s/base/logging/fluent-bit-values.yaml

# Upgrades later:
helm upgrade loki grafana/loki --namespace logging -f infra/k8s/base/logging/loki-values.yaml
helm upgrade fluent-bit fluent/fluent-bit --namespace logging -f infra/k8s/base/logging/fluent-bit-values.yaml
```

Grafana (installed in the `monitoring` namespace by
`../monitoring/prometheus-values.yaml`) is already pre-wired with a Loki
datasource pointed at `http://loki.logging.svc.cluster.local:3100` via
`grafana.additionalDataSources`, so logs are queryable/correlatable
alongside the metrics dashboards without extra setup once both stacks are
installed.

## Validation performed

Same caveat as monitoring: no `helm` binary or live cluster in this
environment. `kubectl kustomize infra/k8s/base/logging` was run to confirm
`namespace.yaml`/`kustomization.yaml` parse correctly; `loki-values.yaml`
and `fluent-bit-values.yaml` were hand-checked for YAML syntax and
cross-referenced against each chart's documented value schema from memory,
not `helm template`-verified. Run `helm template` against both before the
first real install and pin exact chart versions in the commands above
(this README intentionally doesn't pin one so it doesn't go stale, but your
actual `helm install` commands should).
