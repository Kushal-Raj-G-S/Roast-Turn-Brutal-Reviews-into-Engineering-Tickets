-- Staging: one row per pipeline run, tagged by pipeline_version.
-- This is the table regression_detection.sql diffs across v1/v2/v3
-- shadow deployments.

select
    upload_id,
    tenant_id,
    total_reviews,
    filtered_noise,
    actionable_reviews,
    clusters_created,
    processing_time_ms,
    pipeline_version,
    created_at
from {{ source('roast_warehouse', 'upload_metrics') }}
