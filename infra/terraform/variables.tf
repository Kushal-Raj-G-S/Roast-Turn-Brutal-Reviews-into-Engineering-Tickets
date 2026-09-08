variable "project_id" {
  description = "GCP project id"
  type        = string
}

variable "region" {
  description = "GCP region for the staging bucket"
  type        = string
  default     = "us-central1"
}

variable "bigquery_dataset" {
  description = "BigQuery dataset name (must match Config.BIGQUERY_DATASET)"
  type        = string
  default     = "roast_warehouse"
}

variable "bigquery_location" {
  description = "BigQuery dataset location (must match Config.BIGQUERY_LOCATION)"
  type        = string
  default     = "US"
}

variable "partition_expiration_days" {
  description = "Days before a table partition expires. Caps unbounded storage growth."
  type        = number
  default     = 365
}

variable "k8s_namespace" {
  description = "Kubernetes namespace running the backend (for Workload Identity binding)"
  type        = string
  default     = "default"
}

variable "k8s_service_account" {
  description = "Kubernetes service account name the backend pods run as"
  type        = string
  default     = "roast-backend"
}
