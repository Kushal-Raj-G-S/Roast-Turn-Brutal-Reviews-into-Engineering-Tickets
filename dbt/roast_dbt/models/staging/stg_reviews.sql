-- Staging: one row per review, off the warehouse `reviews` table that
-- BigQueryWarehouseSink loads from staged Parquet. Light typing/renaming
-- only — business logic lives in the marts layer, so a source schema
-- change touches exactly one file.
--
-- Note: the raw 384-float embedding is deliberately not in the warehouse
-- (Qdrant owns vector search; storing vectors here would inflate
-- bytes-billed on every scan). Only dimension/model are kept, for lineage.

{{ config(
    materialized='view'
) }}

select
    id as review_id,
    upload_id,
    tenant_id,
    text,
    rating,
    version as app_version,
    device,
    review_date,
    is_verified,
    is_actionable,
    actionability_score,
    actionability_confidence,
    embedding_dimension,
    embedding_model,
    cluster_id,
    created_at,
    ingested_at
from {{ source('roast_warehouse', 'reviews') }}
where text is not null
