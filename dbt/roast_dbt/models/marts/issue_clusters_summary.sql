-- Mart: one row per cluster with an actionability-weighted priority score.
--
-- This replaces an ad-hoc Python aggregation that scanned a Postgres table
-- on every dashboard load. Now it's versioned, tested SQL materialized
-- once per DAG cycle, and the dashboard reads the result.
--
-- Incremental + partitioned because a full rebuild rescans every review
-- ever ingested, and BigQuery bills by bytes scanned — at 200K+ rows per
-- upload that is the difference between cents and dollars per run.

{{ config(
    materialized='incremental',
    unique_key='cluster_id',
    partition_by={'field': 'ingested_at', 'data_type': 'timestamp', 'granularity': 'day'},
    cluster_by=['tenant_id'],
    incremental_strategy='merge'
) }}

with clusters as (
    select * from {{ ref('stg_clusters') }}
    {% if is_incremental() %}
      where ingested_at >= (
          select coalesce(max(ingested_at), timestamp('1970-01-01')) from {{ this }}
      )
    {% endif %}
),

-- Only roll up reviews belonging to the clusters in scope this run, so the
-- incremental build doesn't scan the full reviews table.
review_rollup as (
    select
        cluster_id,
        count(*) as actual_review_count,
        countif(is_actionable) as actionable_count,
        avg(actionability_score) as avg_actionability
    from {{ ref('stg_reviews') }}
    where cluster_id is not null
      and cluster_id in (select cluster_id from clusters)
    group by cluster_id
)

select
    c.tenant_id,
    c.cluster_id,
    c.issue_fingerprint,
    c.title,
    c.severity,
    c.status,
    c.review_count,
    r.actionable_count,
    r.avg_actionability,
    c.avg_rating,
    -- 4-signal priority score: volume, severity, actionability, rating.
    -- Weights sum to 1.0; each term is normalized to 0-1 before weighting
    -- so no single signal can dominate through raw magnitude.
    round(
        (least(c.review_count / 100.0, 1.0) * 0.25)
        + (case c.severity
             when 'critical' then 1.0
             when 'high' then 0.75
             when 'medium' then 0.5
             else 0.25
           end * 0.35)
        + (coalesce(r.avg_actionability, 0) * 0.25)
        + ((5 - coalesce(c.avg_rating, 3)) / 5 * 0.15)
    , 4) as priority_score,
    c.affected_versions,
    c.keywords,
    c.created_at,
    c.ingested_at
from clusters c
left join review_rollup r using (cluster_id)
