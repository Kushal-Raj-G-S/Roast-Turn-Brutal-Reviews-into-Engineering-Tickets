# Roast data platform infrastructure.
#
# Everything the pipeline depends on in GCP, declared rather than clicked
# through the console: the BigQuery dataset + tables, the GCS staging
# bucket (with lifecycle rules so staged Parquet doesn't accumulate cost),
# and a least-privilege service account with Workload Identity binding so
# pods authenticate without a mounted key file.
#
# Apply:  terraform init && terraform apply -var project_id=<your-project>

terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ---------------------------------------------------------------------
# GCS — inter-stage Parquet staging
# ---------------------------------------------------------------------

resource "google_storage_bucket" "staging" {
  name     = "${var.project_id}-roast-staging"
  location = var.region

  uniform_bucket_level_access = true
  force_destroy               = false

  # Staged payloads are intermediate artifacts. The DAG deletes them on a
  # successful run; this is the backstop for failed runs whose artifacts
  # were deliberately kept for post-mortem.
  lifecycle_rule {
    condition {
      age = 14
    }
    action {
      type = "Delete"
    }
  }

  # Embeddings are large and rewritten per run — no point paying standard
  # storage for anything that survives a week.
  lifecycle_rule {
    condition {
      age = 3
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  versioning {
    enabled = false # intermediate data; versioning would just multiply cost
  }
}

# ---------------------------------------------------------------------
# BigQuery — analytical warehouse
# ---------------------------------------------------------------------

resource "google_bigquery_dataset" "warehouse" {
  dataset_id  = var.bigquery_dataset
  location    = var.bigquery_location
  description = "Roast analytical warehouse — review/cluster/run-metric tables read by dbt"

  # Partition expiry caps unbounded growth of raw review history.
  default_partition_expiration_ms = var.partition_expiration_days * 24 * 60 * 60 * 1000

  labels = {
    app       = "roast"
    component = "warehouse"
  }
}

# Tables are created idempotently by BigQueryWarehouseSink.ensure_schema()
# at runtime, but declaring them here means `terraform apply` produces a
# working warehouse before the first pipeline run, and schema drift shows
# up as a plan diff.
resource "google_bigquery_table" "reviews" {
  dataset_id          = google_bigquery_dataset.warehouse.dataset_id
  table_id            = "reviews"
  deletion_protection = true

  time_partitioning {
    type  = "DAY"
    field = "ingested_at"
  }
  clustering = ["tenant_id", "upload_id"]

  schema = file("${path.module}/schemas/reviews.json")
}

resource "google_bigquery_table" "clusters" {
  dataset_id          = google_bigquery_dataset.warehouse.dataset_id
  table_id            = "clusters"
  deletion_protection = true

  time_partitioning {
    type  = "DAY"
    field = "ingested_at"
  }
  clustering = ["tenant_id", "issue_fingerprint"]

  schema = file("${path.module}/schemas/clusters.json")
}

resource "google_bigquery_table" "upload_metrics" {
  dataset_id          = google_bigquery_dataset.warehouse.dataset_id
  table_id            = "upload_metrics"
  deletion_protection = true

  time_partitioning {
    type  = "DAY"
    field = "created_at"
  }
  clustering = ["tenant_id"]

  schema = file("${path.module}/schemas/upload_metrics.json")
}

# ---------------------------------------------------------------------
# Service account — least privilege, Workload Identity (no key files)
# ---------------------------------------------------------------------

resource "google_service_account" "pipeline" {
  account_id   = "roast-pipeline"
  display_name = "Roast pipeline (BigQuery + GCS access)"
}

# jobUser (not dataEditor at project level) — the pipeline needs to RUN
# load/query jobs, and gets write access only to its own dataset below.
resource "google_project_iam_member" "bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_bigquery_dataset_iam_member" "warehouse_editor" {
  dataset_id = google_bigquery_dataset.warehouse.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.pipeline.email}"
}

# Bucket-scoped, not project-scoped storage access.
resource "google_storage_bucket_iam_member" "staging_admin" {
  bucket = google_storage_bucket.staging.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.pipeline.email}"
}

# Lets the GKE Kubernetes service account impersonate this GCP service
# account — so pods get credentials from the metadata server instead of a
# JSON key baked into a secret. This is why embedding-deployment.yaml
# needs no key file mounted.
resource "google_service_account_iam_member" "workload_identity" {
  service_account_id = google_service_account.pipeline.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.k8s_namespace}/${var.k8s_service_account}]"
}
