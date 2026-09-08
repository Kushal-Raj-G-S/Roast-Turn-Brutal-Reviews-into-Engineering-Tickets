-- Staging: one row per cluster (issue), splitting the comma-joined
-- affected_versions/keywords columns back into arrays.
--
-- issue_fingerprint comes through from the warehouse sink and is the
-- stable cross-run identity the regression model partitions by (cluster_id
-- is a per-upload UUID and cannot serve that purpose).

select
    cluster_id,
    upload_id,
    tenant_id,
    title,
    issue_fingerprint,
    severity,
    status,
    review_count,
    avg_rating,
    split(affected_versions, ',') as affected_versions,
    split(keywords, ',') as keywords,
    ai_analyzed,
    created_at,
    ingested_at
from {{ source('roast_warehouse', 'clusters') }}
