# v2.9 Observability — first development increment

This first increment of the v2.9 roadmap provides the operator dashboard and is
included in v3.0.0. No schema migration or new runtime dependency is required.

## Operator dashboard

Open **Observability** using an administrator browser session. The read-only API is
`GET /api/v1/observability`; it requires `audit:read` and an administrator session.
API keys, mobile credentials and non-administrator sessions cannot read it.

- Project-scoped API response-header timing, embedding latency and local model JSON
  request duration: sample count, mean, approximate P95 upper bound and error rate.
- Project document backlog/failures, documents processed in 24 hours and average/hour.
- Project conversation/document candidate acceptance: accepted divided by accepted
  plus rejected, using review timestamps from the last 24 hours. No reviews returns
  no sample, rather than 0% success.
- Project connector enabled/failing/overdue counts, latest sync and 24-hour run totals.
- Deployment-wide document-ingest queue length and started/failed registry sizes.
  Registry entries can await worker cleanup; these are not per-project queue counts.
- Deployment service readiness: PostgreSQL project queries, Redis, S3 readiness and
  the configured Ollama tags endpoint. These checks do not prove bucket permissions,
  successful generation, backup integrity or an external provider's health.

## Measurement boundaries

Timing aggregates use existing Redis, fixed operation names and project UUID
namespaces. Five-minute buckets retain approximately 24 hours and expire after at
most 24 hours 5 minutes. No prompts, answers, document names, raw URLs, query strings,
tokens, user IDs or job payloads are recorded. Redis restarts/data loss can reset
timings; these are best-effort operational counters, not durable billing or SLA data.

P95 is a histogram upper bound, not an exact percentile. API timing ends at response
headers, excludes login/unresolved authentication and the observability endpoint,
and counts HTTP 4xx/5xx as errors. Model timing includes HTTP and JSON parsing, not
later semantic/citation validation. Existing worker project contexts carry model
timings into the same project namespace.

Telemetry writes have bounded Redis timeouts, no retries, and fail open without
changing application return values or exceptions. This does not remove Redis's
existing authentication/rate-limit/queue responsibilities. Readiness probes are
read-only, bounded and never return raw exception strings or configured addresses.
The page refreshes on request rather than polling or running a background monitor.

## Remaining roadmap

- Prometheus export with an explicit authenticated access model.
- Grafana dashboard/provisioning after export definitions are stable.
- Alert thresholds, deduplication and delivery preferences before notifications.
- Longer-term durable trends, explicit worker liveness and richer ingestion stages.

These follow-ups are not part of the initial dashboard and are not marked shipped.
