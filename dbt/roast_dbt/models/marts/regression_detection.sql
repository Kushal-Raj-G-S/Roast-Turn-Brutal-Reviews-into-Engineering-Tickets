-- Mart: cross-version regression detection using window functions.
--
-- THE KEY POINT: this partitions by issue_fingerprint, NOT cluster_id.
-- cluster_id is a fresh UUID per upload, so the same underlying issue has
-- a different cluster_id in every pipeline run — LAG() over cluster_id
-- would never match anything across versions and the model would silently
-- report zero regressions forever. issue_fingerprint (computed in
-- bigquery_sink.compute_issue_fingerprint) is a normalized,
-- order-independent hash of the cluster's title tokens + keywords, so the
-- same issue hashes identically across v1/v2/v3 even as its UUID and
-- review count change.
--
-- A cluster is REGRESSED if, versus the previous pipeline version for the
-- same tenant+fingerprint, its severity worsened or its review volume
-- surged past the tolerance band (a resurfaced bug).

{{ config(
    materialized='incremental',
    unique_key=['tenant_id', 'issue_fingerprint', 'current_pipeline_version'],
    partition_by={'field': 'run_created_at', 'data_type': 'timestamp', 'granularity': 'day'},
    cluster_by=['tenant_id'],
    incremental_strategy='merge'
) }}

with severity_rank as (
    -- Ordinal severity so "got worse" is a numeric comparison rather than
    -- a pile of string cases.
    select 'low' as severity, 1 as rank union all
    select 'medium', 2 union all
    select 'high', 3 union all
    select 'critical', 4
),

runs as (
    select
        m.pipeline_version,
        m.tenant_id,
        m.upload_id,
        m.created_at as run_created_at,
        c.cluster_id,
        c.issue_fingerprint,
        c.title,
        c.severity,
        coalesce(sr.rank, 0) as severity_rank,
        c.review_count
    from {{ ref('stg_upload_metrics') }} m
    join {{ ref('stg_clusters') }} c
        on c.upload_id = m.upload_id
       and c.tenant_id = m.tenant_id
    left join severity_rank sr
        on sr.severity = c.severity

    {% if is_incremental() %}
      -- Only reprocess recent runs, but keep a 30-day lookback so the
      -- LAG() comparison can still see the preceding version's row.
      where m.created_at >= (
          select coalesce(max(run_created_at), timestamp('1970-01-01'))
          from {{ this }}
      ) - interval 30 day
    {% endif %}
),

with_lag as (
    select
        *,
        lag(severity) over w as prev_severity,
        lag(severity_rank) over w as prev_severity_rank,
        lag(review_count) over w as prev_review_count,
        lag(pipeline_version) over w as prev_pipeline_version
    from runs
    window w as (
        partition by tenant_id, issue_fingerprint
        order by run_created_at, pipeline_version
    )
)

select
    tenant_id,
    issue_fingerprint,
    cluster_id as current_cluster_id,
    title,
    prev_pipeline_version,
    pipeline_version as current_pipeline_version,
    prev_severity,
    severity as current_severity,
    prev_review_count,
    review_count as current_review_count,
    review_count - prev_review_count as review_count_delta,
    safe_divide(review_count, prev_review_count) as review_count_ratio,
    case
        when prev_pipeline_version is null then 'NEW'
        when severity_rank > prev_severity_rank then 'REGRESSED_SEVERITY'
        when review_count > prev_review_count * 1.5 then 'REGRESSED_VOLUME'
        when severity_rank < prev_severity_rank
          or review_count < prev_review_count * 0.5 then 'IMPROVED'
        else 'STABLE'
    end as regression_status,
    run_created_at
from with_lag
