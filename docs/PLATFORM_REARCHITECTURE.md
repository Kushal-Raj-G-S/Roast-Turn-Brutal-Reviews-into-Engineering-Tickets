# Roast — Platform Re-architecture (Kafka, Airflow, BigQuery, dbt, GKE)

## Why

Roast's pipeline already had good structure — staged processing, an
`IMessageQueue` port with in-memory and Redis backends, domain events per
stage. It was missing three properties a production data platform needs:

| Gap | Symptom before | Fixed by |
|---|---|---|
| **Durability** | In-memory queue: a restart mid-upload loses the batch | Kafka — durable, replayable log; offsets commit only after handlers succeed |
| **Analytical scale** | Postgres row-storage scanning 200K+ rows for cluster/trend queries | BigQuery — columnar, partitioned by date, clustered by tenant |
| **Recoverability** | One `execute()` call: a clustering failure re-runs embedding for the whole batch | Airflow — per-stage retry, backfill by `upload_id` |

Nothing here replaces working code. `BulkProcessingPipeline`'s stage
methods are untouched — the DAG calls them directly. Postgres remains the
transactional store; BigQuery is added beside it as the analytical sink.

**The default is unchanged behaviour.** `EVENT_BUS_BACKEND` defaults to
`memory`, so nothing switches to Kafka until the env var says so.

## Architecture

```
 upload (bulk CSV / connectors)
        │
        ▼
   Kafka  roast.events.*            durable, replayable, keyed by entity
        │                           failures → roast.events.*.dlq
        ▼
 Airflow DAG  roast_bulk_review_pipeline
   load → filter → score → embed → cluster+persist → warehouse → cleanup
        │            │                    │
        │            │                    ├── Postgres  (OLTP, user-facing)
        │            │                    └── BigQuery  (OLAP, via load job)
        │            ▼
        └──► GCS Parquet staging  (stage handoff; XCom carries only the URI)
                     │
                     ▼
              dbt: staging → marts
                 · issue_clusters_summary   (4-signal priority score)
                 · regression_detection     (LAG over issue_fingerprint)
```

## What was added

| Piece | File | Note |
|---|---|---|
| Kafka backend | `backend/src/infrastructure/messaging/kafka_queue.py` | Third implementation of the existing `IMessageQueue` port; DLQ, idempotent producer, batch-level offset commits |
| Event bus provider | `backend/src/infrastructure/messaging/bus_provider.py` | Process-wide singleton — the pipeline's per-stage event publishes were previously dead code (`event_bus=None` at every call site) |
| Review codec | `backend/src/infrastructure/warehouse/review_codec.py` | Correct round-trip for nested value objects |
| GCS staging | `backend/src/infrastructure/warehouse/gcs_staging.py` | Parquet stage handoff; run-scoped paths so backfills don't overwrite |
| BigQuery sink | `backend/src/infrastructure/warehouse/bigquery_sink.py` | Batch load jobs, idempotent delete-then-load, `compute_issue_fingerprint` |
| dbt project | `dbt/roast_dbt/` | Incremental+partitioned marts, `dbt_utils` tests, source freshness |
| Airflow DAG | `airflow/dags/roast_pipeline_dag.py` | Per-stage retries, exponential backoff, staging cleanup on success only |
| Pipeline factory | `backend/app/core/pipeline_factory.py` | One wiring path shared by the API route and the DAG |
| Terraform | `infra/terraform/` | Dataset, tables, bucket + lifecycle, least-privilege SA, Workload Identity |
| GKE | `backend/Dockerfile`, `k8s/` | Multi-stage image, **CPU-only torch**, startup probe, HPA, PDB, Workload Identity (no key files) |
| Consumers | `backend/src/infrastructure/messaging/consumers.py` | Subscribes to UPLOAD_COMPLETED/FAILED; idempotent via the inbox table |
| Inbox migration | `backend/migrations/create_processed_events.sql` | `(event_id, consumer_name)` claim table for at-least-once dedup |
| CI | `.github/workflows/ci.yml` | 6 blocking jobs: lint+unit, **integration on live services**, terraform+schema-drift, dbt, Docker build, DAG import+structure |

## Design decisions worth defending

**Payloads never go through XCom.** Airflow persists XCom values in its
metadata database (48KB limit on the default backend). Measured: 500
reviews with 384-dim embeddings serialize to **1,174 KB of JSON** — 24×
over the limit, and that's 0.25% of a full 200K batch. Staged as Parquet
it's **53 KB in GCS**, and XCom carries a ~90-byte URI. This was the
single most important correction in the build.

**Batch load jobs, not streaming inserts.** `insert_rows_json()` is billed
per GB, quota-limited, caps requests near 10MB, and leaves rows in a
streaming buffer that isn't immediately partition-pruneable. Load jobs are
free and atomic, and read the Parquet staging already wrote. Streaming is
kept only for the single-row `upload_metrics` insert.

**`regression_detection` partitions by `issue_fingerprint`, not
`cluster_id`.** `cluster_id` is a fresh UUID per upload, so `LAG()` over it
would never match the same issue across v1/v2/v3 and the model would
silently report zero regressions forever. The fingerprint is a normalized,
order-independent hash of title tokens + keywords, so the same issue
hashes identically across runs.

**Raw embeddings are not stored in BigQuery.** Qdrant owns vector search.
Putting 200K × 384 floats in an analytical table inflates bytes-billed for
every query that never touches them. Dimension and model name are kept for
lineage.

**Partition by ingest date, cluster by tenant.** BigQuery bills by bytes
scanned; the daily DAG and dashboard queries then read one partition
instead of the full table.

**At-least-once, not exactly-once.** Offsets commit after handlers
succeed, so a crash in that window replays. That's safe because the sinks
are idempotent by construction (delete-then-load per `upload_id`,
cluster writes keyed by `cluster_id`). Exactly-once would need
transactional produce+consume spanning Postgres and BigQuery — real
complexity for no gain here.

**No CPU limit on the embedding container.** Throttling a burstable,
CPU-bound ONNX workload produces latency cliffs; the request guarantees a
floor and the HPA handles scale-out. Memory *is* limited, because a leak
there should kill the pod.

**Identifier validation in the BigQuery sink.** BigQuery can't parameterize
table names, so the idempotent `DELETE`s must interpolate them. Identifiers
are validated at construction; all values are bound as query parameters.

## Setup

| Step | Install needed |
|---|---|
| Kafka | **None** — point `KAFKA_BOOTSTRAP_SERVERS` at a managed broker (Upstash free tier; Kafka-protocol over SASL_SSL). `aiokafka` is a pip dep. |
| BigQuery / GCS | **None** — free GCP project. `terraform apply` creates dataset, tables, bucket, service account. |
| dbt | `pip install "dbt-core~=1.9.0" "dbt-bigquery~=1.9.0"` in **its own venv**, then `dbt deps`. Pin both — unpinned resolves to a stub with no CLI. |
| Airflow | `pip install apache-airflow` in **its own venv**, then `airflow standalone` (bundles its own SQLite metadata DB) |
| Docker / GKE | Docker for `docker build`; `gcloud` + a cluster only when deploying live |

Airflow and dbt need separate virtualenvs — Airflow pins narrow ranges
across dozens of transitive dependencies and will fight
`backend/requirements.txt`.

### Environment variables

```bash
EVENT_BUS_BACKEND=kafka            # default "memory" — nothing changes until set
KAFKA_BOOTSTRAP_SERVERS=<broker>:9092
KAFKA_SECURITY_PROTOCOL=SASL_SSL
KAFKA_SASL_MECHANISM=SCRAM-SHA-256
KAFKA_SASL_USERNAME=...
KAFKA_SASL_PASSWORD=...
GCP_PROJECT_ID=<project>
GCS_STAGING_BUCKET=<project>-roast-staging
BIGQUERY_DATASET=roast_warehouse
PIPELINE_VERSION=v1               # tags runs for the regression model

# Off by default. Apply migrations/create_processed_events.sql FIRST —
# enabling this without the inbox table sends every event to the DLQ.
EVENT_CONSUMERS_ENABLED=false
```

### Bring-up order

```bash
# 1. Infrastructure
cd infra/terraform && terraform init && terraform apply -var project_id=<project>
terraform output                     # copy values into backend/.env

# 2. Backend tests + lint (both blocking in CI)
cd backend && pytest tests/ -q && ruff check src/infrastructure/ tests/

# 3. Container
docker build -t roast-backend:local ./backend
docker run -p 8000:8000 --env-file backend/.env roast-backend:local

# 4. Airflow (own venv)
airflow standalone
# copy airflow/dags/roast_pipeline_dag.py into the printed dags/ folder,
# then trigger with conf: {"upload_id": <id>}

# 5. dbt (own venv)
cd dbt/roast_dbt && dbt deps && dbt build

# 6. GKE
kubectl apply -f k8s/configmap.example.yaml   # with real values
kubectl apply -f k8s/embedding-deployment.yaml
```

## Verification status

Everything below was executed, not assumed. `-m integration` tests run
against real services in Docker (and in CI via service containers); they
skip themselves when a service is unreachable, and the CI job fails if the
services don't come up.

| Claim | How it was verified | Result |
|---|---|---|
| Kafka publish/consume works | Real `apache/kafka:3.8.0` broker, KRaft mode | Pass |
| Retry increments and eventually succeeds | Flaky handler, asserted counter 0→1→2 | Pass |
| Exhausted retries reach the DLQ, bounded | Poison handler, read `<topic>.dlq` directly | Pass — **found a real bug**, see below |
| Committed offsets survive consumer restart | Second consumer, same group, asserted zero reprocessing | Pass |
| Per-entity ordering holds | 5 messages, same key, asserted sequence | Pass |
| GCS Parquet round-trip loses nothing | `fake-gcs-server`, 50 reviews × 384-dim, float-approx compared | Pass |
| Backfill runs don't overwrite each other | Two run_ids, same upload | Pass |
| Cleanup deletes only its own run | Two runs, one cleaned | Pass |
| Empty batch doesn't break the handoff | Aggressive-filter case | Pass |
| **cluster_id windowing was broken** | BigQuery emulator, real `LAG()` | **Confirmed: all lags NULL, zero regressions detectable** |
| **fingerprint windowing detects regressions** | Same engine, 3 seeded runs | Pass: v1→NEW, v2→REGRESSED_SEVERITY, v3→REGRESSED_VOLUME |
| Improvement isn't misreported as regression | critical/400 → low/20 | Pass: IMPROVED |
| DAG imports cleanly | Real Airflow 2.10.5 `DagBag` | 0 import errors |
| DAG structure is as designed | Task chain, retries, timeouts, trigger rules | 7 tasks, embed `retries=5` + 2h timeout, cleanup `all_success` |
| dbt project is valid | `dbt-core 1.9.11` + `dbt-bigquery 1.9.2`, `deps` + `parse` | 5 models, 20 tests, 3 sources w/ freshness |
| Terraform is valid | `terraform 1.9.8` in Docker | `fmt -check` clean, `validate` success |
| Inbox migration is valid DDL | Applied to real Postgres 16 | Schema matches expectations |
| Redelivery doesn't double-notify | Same event claimed 3× | 1 claim wins, 2 rejected, 1 row |
| Independent consumers each get a claim | Two consumer names, same event | Both claim; neither twice |
| Concurrent replicas can't both win | 8 threads racing one event | Exactly 1 winner, no errors |
| **End-to-end: Kafka → consumer → Postgres** | Same event published 3× | **3 deliveries, side effect ran once** |

Totals: **27 unit + 24 integration = 51 passing**, ruff clean.

### Consumers (the gap that was open, now closed)

`src/infrastructure/messaging/consumers.py` subscribes to
`UPLOAD_COMPLETED` and `UPLOAD_FAILED`. Before it existed, the pipeline
published a domain event at every stage and **nothing read them** — the
events were produced, durably stored, and ignored.

It also fixes a functional gap, not just an architectural one: the **v2
pipeline path never sent the user a completion alert at all.** Only the v1
path (`app/core/shadow_deployment.py`) did, inline. The two paths are
disjoint and only the v2 pipeline publishes these events, so there's no
double-send.

Idempotency is mandatory here, not defensive. Kafka is at-least-once, so
redelivery is a certainty, and a redelivered completion event would
re-send the user's Discord/push/email alert — a bug the user personally
receives. Each handler claims its event in a `processed_events` inbox
table (`migrations/create_processed_events.sql`) via
`INSERT ... ON CONFLICT DO NOTHING` and skips when the claim is lost. The
key is `(event_id, consumer_name)` rather than `event_id` alone, so a
future second consumer isn't starved by whichever consumer claimed first.

Enabled by `EVENT_CONSUMERS_ENABLED` (**default off**) — turning it on
before applying the migration would send every consumed event to the DLQ.

### Bugs real testing caught

`stop_consuming()` originally cancelled consumer tasks immediately and then
stopped the producer. If a message exhausted its retries at the same moment
shutdown began, `_publish_to_dlq()` was cancelled mid-send and the producer
closed underneath it — **the permanently-failed message vanished instead of
landing on the dead-letter topic.** Every deploy or pod eviction was a
chance to silently lose exactly the messages you most need to keep.

Unit tests could never have found this: they never open a socket. The fix
is a graceful drain — clear `is_consuming`, wait out a grace period for
each loop to finish its current batch, force-cancel only stragglers, and
stop the producer last. Side benefit: the integration suite got faster
(32s → 15s) because retry thrash disappeared.

**2. The container image was pulling several GB of unused CUDA.** Watching
the real `docker build` showed it downloading `nvidia-cublas` (423 MB),
`cuda-cupti`, `cuda-nvrtc` (90 MB), cudnn and nccl. On Linux, plain
`pip install torch` resolves to the **GPU** build and pulls the whole
NVIDIA runtime — into an image whose inference is CPU-only by design
(`faiss-cpu`, ONNX int8 on CPU). The cost isn't only disk: multi-GB image
pulls make GKE node startup slow, which directly undermines the HPA that
was added to absorb bursts. Fixed by installing torch from PyTorch's
CPU wheel index in its own cached layer. My multi-stage split was treating
a much smaller symptom than the real cause.

**3. `pip install dbt-bigquery` unpinned installs a dbt that cannot run
dbt.** It resolved to `dbt-core-experimental-parser 2.0.0rc1` with no
dbt-core and no CLI entrypoint — an install that exits 0 and then has no
`dbt` command. CI now pins `dbt-core~=1.9.0` and `dbt-bigquery~=1.9.0`.

### Measured, not estimated

```
100 reviews × 384-dim embeddings
  JSON:    494 KB      ← what the first version pushed through XCom
  Parquet:  52 KB      (9.5× smaller, in GCS)
  XCom limit: 48 KB    ← JSON exceeded it 10×, at 0.05% of a real batch
```

## Interview talking points

**Why Kafka over scaling Redis?** Durability and replay. Redis Streams
work at moderate scale, but Kafka's committed-offset model means a
consumer crash resumes rather than loses. Manual commits make "done" mean
"every handler succeeded."

**Why BigQuery over tuning Postgres?** Name the query shape: full-table
analytical scans over 200K+ rows are columnar territory. Bring one
measured before/after number for a cluster aggregation.

**Why does the DAG call private stage methods rather than `execute()`?**
So each stage retries and is inspectable independently. `execute()` still
serves the interactive API path; both share `build_bulk_pipeline()` so the
dependency wiring is never forked.

**What broke first when you built this?** Good answer to have ready: XCom.
Explain the 48KB limit, the 1.17MB-per-500-reviews measurement, and the
move to Parquet-in-GCS with URI-only XCom. It shows you found a real
scaling bug by reasoning about the platform, not by guessing.

## Honest remaining gaps

- **Not deployed to GKE.** Dockerfile, manifests and Terraform are
  complete and validated, and the image builds — but nothing is running on
  a cluster. `gcloud` + `terraform apply` + `kubectl apply` is the
  remaining step. **Don't claim live GKE experience until it's actually
  running.**
- **BigQuery and GCS were tested against emulators, not real GCP.** The
  emulators cover SQL semantics and the storage round-trip, but not IAM,
  Workload Identity, partition pruning, real load-job behaviour, or
  billing. Those need a real (free-tier) GCP project.
- **The full DAG has never executed end to end.** Its structure, imports
  and every component it calls are tested, but no run has gone
  load → filter → score → embed → cluster → warehouse against real
  services with a real upload. That needs the GCP project above.
- **Consumers are off by default.** `EVENT_CONSUMERS_ENABLED=false` until
  `migrations/create_processed_events.sql` is applied. The code and its
  idempotency are tested; the switch is deliberately not flipped.
- **`load_reviews_from_gcs` ignores extra Parquet columns** via
  `ignore_unknown_values`. Deliberate (staging carries the raw embedding
  the warehouse drops), but it also means a genuine schema typo loads
  silently instead of failing. A stricter explicit projection would be
  better.
- **dbt source freshness is configured but unmonitored** — nothing alerts
  on a warn/error state yet.
- **`processed_events` has no retention job.** The cleanup SQL is
  documented in the migration but isn't scheduled.

## Local test-services cheat sheet

The integration suite needs four containers. All ephemeral, all safe to
delete. The tests skip themselves if a service is missing, so run only
what you need.

```bash
# Kafka (KRaft, no Zookeeper)
docker run -d --name roast-kafka-test -p 9092:9092 \
  -e KAFKA_NODE_ID=1 -e KAFKA_PROCESS_ROLES=broker,controller \
  -e KAFKA_LISTENERS=PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093 \
  -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092 \
  -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER \
  -e KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT \
  -e KAFKA_CONTROLLER_QUORUM_VOTERS=1@localhost:9093 \
  -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 \
  -e KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1 \
  -e KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1 \
  -e KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS=0 \
  apache/kafka:3.8.0

# GCS (needs CLI flags, hence not a compose service)
docker run -d --name roast-gcs-test -p 4443:4443 \
  fsouza/fake-gcs-server:latest \
  -scheme http -port 4443 -external-url http://localhost:4443 -backend memory

# BigQuery
docker run -d --name roast-bq-test -p 9050:9050 \
  ghcr.io/goccy/bigquery-emulator:latest \
  --project=test-project --dataset=roast_warehouse

# Postgres — port 55432 on purpose, so it can never be confused with a
# local 5432 instance or the real DATABASE_URL
docker run -d --name roast-pg-test -p 55432:5432 \
  -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=roast_test \
  postgres:16-alpine
```

Then:

```bash
cd backend
pytest tests/ -m "not integration"   # fast, offline
pytest tests/integration/ -v         # against the containers above
```

Tear down:

```bash
docker rm -f roast-kafka-test roast-gcs-test roast-bq-test roast-pg-test
```

Note: the integration tests **skip** rather than fail when a service is
absent, which means a locally green run can hide a service that never
started. CI guards against this with an explicit port check that fails the
job before the tests run — check for `skipped` in local output.
