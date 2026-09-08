# Values to copy into backend/.env after `terraform apply`.

output "env_gcp_project_id" {
  description = "Set as GCP_PROJECT_ID"
  value       = var.project_id
}

output "env_gcs_staging_bucket" {
  description = "Set as GCS_STAGING_BUCKET"
  value       = google_storage_bucket.staging.name
}

output "env_bigquery_dataset" {
  description = "Set as BIGQUERY_DATASET"
  value       = google_bigquery_dataset.warehouse.dataset_id
}

output "pipeline_service_account_email" {
  description = "Annotate the Kubernetes service account with this for Workload Identity"
  value       = google_service_account.pipeline.email
}

output "k8s_service_account_annotation" {
  description = "Exact annotation to add to the Kubernetes ServiceAccount"
  value       = "iam.gke.io/gcp-service-account=${google_service_account.pipeline.email}"
}
