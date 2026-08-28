"use client";

/**
 * Analytics Page - Review Analytics Dashboard
 * ============================================
 * Real-time insights and metrics from processed reviews
 */

import { motion, AnimatePresence } from "framer-motion";
import { 
  BarChart3, 
  TrendingUp, 
  PieChart, 
  Activity,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Target,
  Flame,
  FileText,
  ChevronDown,
  ChevronUp,
  Star,
  Layers,
  Sparkles,
  ArrowRight,
  Ticket,
  Zap,
  RotateCcw,
  Loader2,
  Download,
  FileSpreadsheet,
  HelpCircle,
  FlaskConical,
} from "lucide-react";
import { useEffect, useState, useMemo, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { apiClient } from "@/lib/api-client";
import { supabase } from "@/lib/supabase/client";
import { SpotlightCard } from "@/components/ui";
import { TicketExportModal } from "@/components/ui/TicketExportModal";
import { AgentAnalysisPanel } from "@/components/ui/AgentAnalysisPanel";
import type { ClusterDetail, AgentMetadata } from "@/lib/api-client";

type AnalyticsData = {
  user_statistics: {
    total_reviews_analyzed: number;
    total_issues_found: number;
    total_issues_resolved: number;
    average_sentiment_score: number;
    rating_1_count: number;
    rating_2_count: number;
    rating_3_count: number;
    rating_4_count: number;
    rating_5_count: number;
    average_resolution_time_hours: number;
    last_analysis_at?: string;
  };
  severity_distribution: {
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
  status_distribution: {
    fresh_roast: number;
    assigned: number;
    in_progress: number;
    resolved: number;
    wont_fix: number;
  };
  recent_activity: Array<{
    date: string;
    filename: string;
    reviews: number;
    clusters: number;
  }>;
  total_uploads: number;
  clusters?: Array<{
    id: number;
    title: string;
    severity: string;
    review_count: number;
    status: string;
    created_at: string;
    regression_detected?: boolean;
    regression_of_title?: string;
    regression_confidence?: number;
    regression_match_method?: string;
    ai_metadata?: AgentMetadata | null;
  }>;
  upload_data?: {
    filename: string;
    processing_time_seconds?: number;
    total_reviews?: number;
    filtered_noise?: number;
  };
};

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainingSeconds}s`;
}

export default function AnalyticsPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const uploadId = searchParams?.get('upload_id');
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedClusters, setExpandedClusters] = useState<Set<number>>(new Set());
  const [clusterDetails, setClusterDetails] = useState<Map<number, ClusterDetail>>(new Map());
  const [exportCluster, setExportCluster] = useState<NonNullable<AnalyticsData['clusters']>[number] | null>(null);
  const [loadingExportId, setLoadingExportId] = useState<number | null>(null);
  const [exportingReport, setExportingReport] = useState<"csv" | "pdf" | null>(null);
  const [reportExportError, setReportExportError] = useState<string | null>(null);
  // Whether the RCA/RAGAS enrichment poll gave up without ever seeing full
  // enrichment land -- distinct from "still polling normally", shown as a
  // softer "taking longer than usual" note instead of an active spinner.
  const [aiEnrichmentGaveUp, setAiEnrichmentGaveUp] = useState(false);

  // ── Triage queue / cross-platform / test stubs ────────────────────────────
  // 'severity' = the original bucketed view. 'triage' = one flat list ranked
  // by the backend's fused priority score (severity + AI-evidence
  // faithfulness + regression signal + volume), so "what do I fix first"
  // doesn't have to be re-derived by eye from four separate badges.
  const [sortMode, setSortMode] = useState<'severity' | 'triage'>('severity');
  const [triageScores, setTriageScores] = useState<Map<number, { score: number; breakdown: Record<string, number> }>>(new Map());
  const [crossPlatform, setCrossPlatform] = useState<Array<{
    android_cluster_id: number; android_title: string;
    ios_cluster_id: number; ios_title: string; confidence: number;
  }>>([]);
  const [testStubs, setTestStubs] = useState<Map<number, string>>(new Map());
  const [loadingStubId, setLoadingStubId] = useState<number | null>(null);
  const [stubError, setStubError] = useState<Map<number, string>>(new Map());

  // Mark resolved / reopen -- previously there was no way to do this
  // anywhere in the product (no API, no UI), which meant the fix-
  // verification loop had no real trigger a user could actually reach.
  const [resolvingId, setResolvingId] = useState<number | null>(null);
  const toggleResolved = async (cluster: NonNullable<AnalyticsData['clusters']>[number]) => {
    const nextStatus = cluster.status === 'resolved' ? 'fresh_roast' : 'resolved';
    setResolvingId(cluster.id);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (session?.access_token) apiClient.setToken(session.access_token);
      await apiClient.updateClusterStatus(cluster.id, nextStatus);
      setAnalytics((prev) => {
        if (!prev?.clusters) return prev;
        return {
          ...prev,
          clusters: prev.clusters.map((c) => (c.id === cluster.id ? { ...c, status: nextStatus } : c)),
        };
      });
    } catch (err) {
      console.error('Failed to update cluster status:', err);
    } finally {
      setResolvingId(null);
    }
  };

  // Fetch the fused triage ranking + best-effort cross-platform pairs for this
  // upload. Both are additive: if either fails the page renders exactly as it
  // did before, just without that extra signal.
  useEffect(() => {
    if (!uploadId) return;
    let cancelled = false;
    (async () => {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session?.access_token || cancelled) return;
      apiClient.setToken(session.access_token);

      apiClient.getTriageQueue(Number(uploadId))
        .then((res) => {
          if (cancelled) return;
          const m = new Map<number, { score: number; breakdown: Record<string, number> }>();
          for (const c of res.clusters ?? []) {
            m.set(c.id, { score: c.priority_score, breakdown: c.priority_breakdown ?? {} });
          }
          setTriageScores(m);
        })
        .catch(() => { /* additive signal — silent */ });

      apiClient.getCrossPlatformMatches(Number(uploadId))
        .then((res) => { if (!cancelled) setCrossPlatform(res.matches ?? []); })
        .catch(() => { /* additive signal — silent */ });
    })();
    return () => { cancelled = true; };
  }, [uploadId]);

  const generateStub = async (clusterId: number) => {
    setLoadingStubId(clusterId);
    setStubError((prev) => { const n = new Map(prev); n.delete(clusterId); return n; });
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (session?.access_token) apiClient.setToken(session.access_token);
      const res = await apiClient.generateTestStub(clusterId);
      setTestStubs((prev) => new Map(prev).set(clusterId, res.code));
    } catch (e: any) {
      setStubError((prev) => new Map(prev).set(clusterId, e?.message || 'Generation failed'));
    } finally {
      setLoadingStubId(null);
    }
  };

  // ── AI enrichment pending banner ──────────────────────────────────────────
  // The page loads with clusters as soon as v1 processing finishes, but the
  // RCA agent + RAGAS scoring (ai_metadata: recurring/speculative/well-
  // supported/severity-adjusted badges, the full AgentAnalysisPanel) runs as
  // a SEPARATE background phase afterwards. Without a visible indicator, a
  // user landing on the page in that window sees what looks like a finished
  // result and has no reason to expect more — the polling elsewhere on this
  // page updates the data, but silently, easy to miss if you're not staring
  // at the page. This banner makes the "more is coming" state explicit.
  const aiEnrichmentPending = useMemo(() => {
    if (!uploadId || aiEnrichmentGaveUp) return false;
    const clusters = analytics?.clusters;
    if (!clusters || clusters.length === 0) return false;
    const eligibleCount = Math.min(
      5,
      clusters.filter(c => c.severity === 'critical' || c.severity === 'high').length
    );
    if (eligibleCount === 0) return false;
    const enrichedCount = clusters.filter(c => c.ai_metadata).length;
    return enrichedCount < eligibleCount;
  }, [uploadId, analytics?.clusters, aiEnrichmentGaveUp]);

  // â”€â”€ Velocity Spike Detection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  // Within an upload, a cluster is "SPIKING" when its review count is
  // at least 1.5 standard deviations above the mean AND â‰¥ 15 reviews.
  // This surfaces outlier clusters that are growing unusually fast.
  const spikeIds = useMemo(() => {
    const clusters = analytics?.clusters ?? [];
    if (clusters.length < 3) return new Set<number>();
    const counts = clusters.map(c => c.review_count ?? 0);
    const mean = counts.reduce((a, b) => a + b, 0) / counts.length;
    const variance = counts.map(c => (c - mean) ** 2).reduce((a, b) => a + b, 0) / counts.length;
    const stddev = Math.sqrt(variance);
    const threshold = Math.max(mean + 1.5 * stddev, 15);
    return new Set(
      clusters.filter(c => (c.review_count ?? 0) >= threshold).map(c => c.id)
    );
  }, [analytics?.clusters]);

  // â”€â”€ Ticket Export helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const openExport = useCallback(async (cluster: NonNullable<AnalyticsData['clusters']>[number]) => {
    if (!clusterDetails.has(cluster.id)) {
      setLoadingExportId(cluster.id);
      try {
        const { data: { session } } = await supabase.auth.getSession();
        if (session) {
          apiClient.setToken(session.access_token);
          const details = await apiClient.getCluster(cluster.id);
          setClusterDetails(prev => new Map(prev.set(cluster.id, details)));
        }
      } catch (err) {
        console.error('Failed to fetch cluster details for export:', err);
      } finally {
        setLoadingExportId(null);
      }
    }
    setExportCluster(cluster);
  }, [clusterDetails]);

  // ── CSV Export with AI Debug Info ────────────────────────────────────────────
  const exportToCSV = useCallback(async () => {
    if (!analytics) return;
    setReportExportError(null);
    setExportingReport("csv");

    try {
    const { user_statistics, severity_distribution, clusters, upload_data } = analytics;

    // Fetch full cluster details if needed
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) throw new Error("Your session expired — please refresh and sign in again.");

    apiClient.setToken(session.access_token);

    // Fetch details for all clusters
    const clusterDetailsPromises = (clusters || []).map(c =>
      apiClient.getCluster(c.id).catch(() => null)
    );
    const clusterDetailsList = await Promise.all(clusterDetailsPromises);

    // Create CSV content
    let csvContent = "";

    // Header
    csvContent += `Analytics Report${uploadId ? ` - ${upload_data?.filename || `Upload #${uploadId}`}` : ''}\n`;
    csvContent += `Generated: ${new Date().toLocaleString()}\n\n`;
    
    // Overview Stats
    csvContent += "OVERVIEW\n";
    csvContent += "Metric,Value\n";
    csvContent += `Total Reviews Analyzed,${user_statistics.total_reviews_analyzed}\n`;
    csvContent += `Total Issues Found,${user_statistics.total_issues_found}\n`;
    csvContent += `Issues Resolved,${user_statistics.total_issues_resolved}\n`;
    if (upload_data?.processing_time_seconds) {
      csvContent += `Processing Time (seconds),${upload_data.processing_time_seconds}\n`;
    }
    csvContent += "\n";
    
    // Severity Distribution
    csvContent += "SEVERITY DISTRIBUTION\n";
    csvContent += "Severity,Count\n";
    csvContent += `Critical,${severity_distribution.critical}\n`;
    csvContent += `High,${severity_distribution.high}\n`;
    csvContent += `Medium,${severity_distribution.medium}\n`;
    csvContent += `Low,${severity_distribution.low}\n`;
    csvContent += "\n";
    
    // Clusters/Issues with AI Debug Info
    if (clusters && clusters.length > 0) {
      csvContent += "ISSUES/CLUSTERS DETAIL\n";
      csvContent += "Title,Severity,Status,Review Count,Regression,RCA Hypothesis,Affected Versions,Affected Devices,Keywords,Sample Reviews (Top 3)\n";
      clusters.forEach((cluster, idx) => {
        const details = clusterDetailsList[idx];
        const title = `"${cluster.title.replace(/"/g, '""')}"`;
        const regression = cluster.regression_detected ? `Yes - ${cluster.regression_of_title}` : 'No';
        const rca = details?.rca_hypothesis ? `"${details.rca_hypothesis.replace(/"/g, '""')}"` : 'N/A';
        const versions = details?.affected_versions?.join('; ') || 'N/A';
        const devices = details?.affected_devices?.join('; ') || 'N/A';
        const keywords = details?.keywords?.join('; ') || 'N/A';
        const samples = details?.sample_reviews?.slice(0, 3).map(r => r.content.substring(0, 100)).join(' | ') || 'N/A';
        const samplesCleaned = `"${samples.replace(/"/g, '""').replace(/\n/g, ' ')}"`;
        csvContent += `${title},${cluster.severity},${cluster.status},${cluster.review_count},${regression},${rca},${versions},${devices},${keywords},${samplesCleaned}\n`;
      });
    }
    
    // Download via Blob — a data: URI silently truncates past a few MB in
    // some browsers, which a report with many clusters + sample reviews can hit.
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8" });
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = `analytics-report-${uploadId || 'all'}-${Date.now()}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(blobUrl);
    } catch (err) {
      setReportExportError(err instanceof Error ? err.message : "Couldn't export CSV. Please try again.");
    } finally {
      setExportingReport(null);
    }
  }, [analytics, uploadId]);

  // ── PDF Export with AI Debug Info ────────────────────────────────────────────
  const exportToPDF = useCallback(async () => {
    if (!analytics) return;
    setReportExportError(null);
    setExportingReport("pdf");

    // Open the window synchronously (before any await) so it isn't caught by
    // popup blockers, which only allow-list windows opened directly from a
    // click handler — opening it after the awaited fetches below gets
    // blocked silently, which is exactly what was happening before this fix.
    const printWindow = window.open('', '_blank');

    try {
    const { user_statistics, severity_distribution, clusters, upload_data } = analytics;

    if (!printWindow) {
      throw new Error("Your browser blocked the report popup — allow popups for this site and try again.");
    }

    // Fetch full cluster details if needed
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) throw new Error("Your session expired — please refresh and sign in again.");

    apiClient.setToken(session.access_token);

    // Fetch details for all clusters
    const clusterDetailsPromises = (clusters || []).map(c =>
      apiClient.getCluster(c.id).catch(() => null)
    );
    const clusterDetailsList = await Promise.all(clusterDetailsPromises);

    const html = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Analytics Report${uploadId ? ` - ${upload_data?.filename || `Upload #${uploadId}`}` : ''}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      padding: 40px;
      background: white;
      color: #1a1a1a;
      font-size: 12px;
    }
    h1 { font-size: 28px; margin-bottom: 8px; color: #ff5500; }
    h2 { font-size: 20px; margin-top: 32px; margin-bottom: 16px; color: #333; border-bottom: 2px solid #ff5500; padding-bottom: 8px; }
    h3 { font-size: 16px; margin-top: 20px; margin-bottom: 12px; color: #444; }
    .subtitle { color: #666; font-size: 14px; margin-bottom: 32px; }
    .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 32px; }
    .stat-card { border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px; }
    .stat-label { font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }
    .stat-value { font-size: 32px; font-weight: bold; color: #ff5500; margin-top: 8px; }
    table { width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 11px; }
    th, td { text-align: left; padding: 10px; border-bottom: 1px solid #e0e0e0; vertical-align: top; }
    th { background: #f5f5f5; font-weight: 600; color: #333; }
    .severity-critical { color: #dc2626; font-weight: 600; }
    .severity-high { color: #ea580c; font-weight: 600; }
    .severity-medium { color: #ca8a04; font-weight: 600; }
    .severity-low { color: #0891b2; font-weight: 600; }
    .badge { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: 600; text-transform: uppercase; margin-left: 8px; }
    .badge-regression { background: #fef3c7; color: #92400e; }
    .cluster-detail { margin-bottom: 24px; padding: 16px; border: 1px solid #e0e0e0; border-radius: 8px; page-break-inside: avoid; }
    .cluster-title { font-size: 14px; font-weight: 600; color: #333; margin-bottom: 12px; }
    .detail-section { margin-bottom: 12px; }
    .detail-label { font-size: 10px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
    .detail-value { color: #333; line-height: 1.6; }
    .detail-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
    .tag { display: inline-block; padding: 4px 8px; background: #f5f5f5; border: 1px solid #e0e0e0; border-radius: 4px; font-size: 10px; }
    .sample-review { padding: 8px; background: #f9fafb; border-left: 3px solid #ff5500; margin-bottom: 8px; font-style: italic; color: #555; }
    @media print {
      body { padding: 20px; }
      .no-print { display: none; }
    }
  </style>
</head>
<body>
  <h1>📊 Analytics Report with AI Debug Info</h1>
  <p class="subtitle">
    ${uploadId ? `Upload: ${upload_data?.filename || `#${uploadId}`} | ` : ''}
    Generated: ${new Date().toLocaleString()}
  </p>

  <h2>Overview</h2>
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">Total Reviews</div>
      <div class="stat-value">${user_statistics.total_reviews_analyzed.toLocaleString()}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Issues Found</div>
      <div class="stat-value">${user_statistics.total_issues_found}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Issues Resolved</div>
      <div class="stat-value">${user_statistics.total_issues_resolved}</div>
    </div>
    ${upload_data?.processing_time_seconds ? `
    <div class="stat-card">
      <div class="stat-label">Processing Time</div>
      <div class="stat-value">${upload_data.processing_time_seconds}s</div>
    </div>
    ` : ''}
  </div>

  <h2>Severity Distribution</h2>
  <table>
    <thead>
      <tr>
        <th>Severity</th>
        <th>Count</th>
        <th>Percentage</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td class="severity-critical">Critical</td>
        <td>${severity_distribution.critical}</td>
        <td>${user_statistics.total_issues_found ? Math.round((severity_distribution.critical / user_statistics.total_issues_found) * 100) : 0}%</td>
      </tr>
      <tr>
        <td class="severity-high">High</td>
        <td>${severity_distribution.high}</td>
        <td>${user_statistics.total_issues_found ? Math.round((severity_distribution.high / user_statistics.total_issues_found) * 100) : 0}%</td>
      </tr>
      <tr>
        <td class="severity-medium">Medium</td>
        <td>${severity_distribution.medium}</td>
        <td>${user_statistics.total_issues_found ? Math.round((severity_distribution.medium / user_statistics.total_issues_found) * 100) : 0}%</td>
      </tr>
      <tr>
        <td class="severity-low">Low</td>
        <td>${severity_distribution.low}</td>
        <td>${user_statistics.total_issues_found ? Math.round((severity_distribution.low / user_statistics.total_issues_found) * 100) : 0}%</td>
      </tr>
    </tbody>
  </table>

  ${clusters && clusters.length > 0 ? `
  <h2>Detailed Issues & Clusters with AI Debug Info</h2>
  ${clusters.map((cluster, idx) => {
    const details = clusterDetailsList[idx];
    return `
      <div class="cluster-detail">
        <div class="cluster-title">
          <span class="severity-${cluster.severity}">${cluster.severity.toUpperCase()}</span> | 
          ${cluster.title}
          ${cluster.regression_detected ? '<span class="badge badge-regression">REGRESSION</span>' : ''}
        </div>
        
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 12px;">
          <div>
            <div class="detail-label">Status</div>
            <div class="detail-value">${cluster.status.replace(/_/g, ' ')}</div>
          </div>
          <div>
            <div class="detail-label">Review Count</div>
            <div class="detail-value">${cluster.review_count} reviews</div>
          </div>
          <div>
            <div class="detail-label">Detected</div>
            <div class="detail-value">${new Date(cluster.created_at).toLocaleDateString()}</div>
          </div>
        </div>

        ${details?.rca_hypothesis ? `
        <div class="detail-section">
          <div class="detail-label">🔍 Root Cause Analysis (RCA)</div>
          <div class="detail-value">${details.rca_hypothesis}</div>
        </div>
        ` : ''}

        ${details?.affected_versions && details.affected_versions.length > 0 ? `
        <div class="detail-section">
          <div class="detail-label">📱 Affected Versions</div>
          <div class="detail-tags">
            ${details.affected_versions.map(v => `<span class="tag">${v}</span>`).join('')}
          </div>
        </div>
        ` : ''}

        ${details?.affected_devices && details.affected_devices.length > 0 ? `
        <div class="detail-section">
          <div class="detail-label">💻 Affected Devices</div>
          <div class="detail-tags">
            ${details.affected_devices.map(d => `<span class="tag">${d}</span>`).join('')}
          </div>
        </div>
        ` : ''}

        ${details?.keywords && details.keywords.length > 0 ? `
        <div class="detail-section">
          <div class="detail-label">🏷️ Keywords</div>
          <div class="detail-tags">
            ${details.keywords.slice(0, 8).map(k => `<span class="tag">${k}</span>`).join('')}
          </div>
        </div>
        ` : ''}

        ${details?.sample_reviews && details.sample_reviews.length > 0 ? `
        <div class="detail-section">
          <div class="detail-label">💬 Sample Reviews (Top 3)</div>
          ${details.sample_reviews.slice(0, 3).map(review => `
            <div class="sample-review">
              "${review.content.substring(0, 200)}${review.content.length > 200 ? '...' : ''}"
              ${review.rating ? ` — ⭐ ${review.rating}/5` : ''}
            </div>
          `).join('')}
        </div>
        ` : ''}
      </div>
    `;
  }).join('')}
  ` : ''}

  <div class="no-print" style="margin-top: 40px; text-align: center;">
    <button onclick="window.print()" style="padding: 12px 24px; background: #ff5500; color: white; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer;">
      Print / Save as PDF
    </button>
    <button onclick="window.close()" style="margin-left: 12px; padding: 12px 24px; background: #666; color: white; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer;">
      Close
    </button>
  </div>
</body>
</html>
    `;
    
    printWindow.document.write(html);
    printWindow.document.close();
    } catch (err) {
      printWindow?.close();
      setReportExportError(err instanceof Error ? err.message : "Couldn't export PDF. Please try again.");
    } finally {
      setExportingReport(null);
    }
  }, [analytics, uploadId]);

  useEffect(() => {
    fetchAnalytics();
  }, [uploadId]);

  // ── Poll for AI enrichment landing in the background ─────────────────────
  // The page loads with clusters as soon as v1/v2 processing finishes, but
  // the RCA agent + RAGAS scoring (ai_metadata: recurring/speculative/
  // well-supported/severity-adjusted badges, the full AgentAnalysisPanel)
  // runs as a SEPARATE background phase afterwards, and only ever targets
  // the top 5 CRITICAL/HIGH clusters (backend: MAX_CLUSTERS_FOR_RCA) — most
  // of the ~20 persisted clusters never get ai_metadata by design. So we
  // can't wait for "every cluster has it"; that would poll the full budget
  // below on almost every upload. Instead wait for however many of the
  // CRITICAL/HIGH clusters (up to 5) are actually eligible, or give up
  // after ~1 min — generous for that phase even under NVIDIA rate limits.
  useEffect(() => {
    if (!uploadId) return;
    setAiEnrichmentGaveUp(false);
    let cancelled = false;
    let pollCount = 0;
    const MAX_POLLS = 12;
    const MAX_RCA_TARGETS = 5;

    const poll = async () => {
      if (cancelled) return;
      const { data: clustersData } = await supabase
        .from('clusters')
        .select('*')
        .eq('upload_id', uploadId)
        .order('severity', { ascending: true });
      if (cancelled || !clustersData) return;

      setAnalytics(prev => (prev ? { ...prev, clusters: clustersData } : prev));

      pollCount++;
      const eligibleCount = Math.min(
        MAX_RCA_TARGETS,
        clustersData.filter((c: { severity?: string }) => c.severity === 'critical' || c.severity === 'high').length
      );
      const enrichedCount = clustersData.filter((c: { ai_metadata?: unknown }) => c.ai_metadata).length;
      const stillPending = clustersData.length === 0 || enrichedCount < eligibleCount;
      if (stillPending && pollCount < MAX_POLLS) {
        timeoutId = setTimeout(poll, 5000);
      } else if (stillPending) {
        // Gave up without ever seeing it land -- tell the user explicitly
        // rather than leaving a spinner running forever or vanishing silently.
        setAiEnrichmentGaveUp(true);
      }
    };

    let timeoutId = setTimeout(poll, 5000);
    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [uploadId]);

  const fetchAnalytics = async () => {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) return;

      const user_id = session.user.id;

      // If upload_id is provided, fetch specific upload's clusters
      if (uploadId) {
        // Fetch upload details
        const { data: uploadData } = await supabase
          .from('uploads')
          .select('*')
          .eq('id', uploadId)
          .eq('user_id', user_id)
          .single();

        // Fetch clusters for this upload
        const { data: clustersData } = await supabase
          .from('clusters')
          .select('*')
          .eq('upload_id', uploadId)
          .order('severity', { ascending: true });

        if (clustersData) {
          // Calculate severity distribution from clusters
          const severityDist = {
            critical: clustersData.filter(c => c.severity === 'critical').length,
            high: clustersData.filter(c => c.severity === 'high').length,
            medium: clustersData.filter(c => c.severity === 'medium').length,
            low: clustersData.filter(c => c.severity === 'low').length,
          };

          setAnalytics({
            user_statistics: {
              total_reviews_analyzed: uploadData?.total_reviews || 0,
              total_issues_found: clustersData.length,
              total_issues_resolved: clustersData.filter(c => c.status === 'resolved').length,
              average_sentiment_score: 0,
              rating_1_count: 0,
              rating_2_count: 0,
              rating_3_count: 0,
              rating_4_count: 0,
              rating_5_count: 0,
              average_resolution_time_hours: 0,
            },
            severity_distribution: severityDist,
            status_distribution: {
              fresh_roast: clustersData.filter(c => c.status === 'fresh_roast').length,
              assigned: 0,
              in_progress: clustersData.filter(c => c.status === 'in_progress').length,
              resolved: clustersData.filter(c => c.status === 'resolved').length,
              wont_fix: 0,
            },
            recent_activity: [],
            total_uploads: 1,
            clusters: clustersData,
            upload_data: {
              filename: uploadData?.filename || '',
              processing_time_seconds: uploadData?.processing_time_seconds,
              total_reviews: uploadData?.total_reviews,
              filtered_noise: uploadData?.filtered_noise,
            }
          });
          
          console.log('[Analytics] Upload data:', {
            upload_id: uploadId,
            total_reviews: uploadData?.total_reviews,
            filtered_noise: uploadData?.filtered_noise,
          });
        }
      } else {
        // Fetch overall analytics
        apiClient.setToken(session.access_token);
        const data = await apiClient.getAnalytics() as AnalyticsData;
        
        // Also fetch all user's clusters
        const { data: userUploads } = await supabase
          .from('uploads')
          .select('id')
          .eq('user_id', user_id);

        if (userUploads && userUploads.length > 0) {
          const uploadIds = userUploads.map(u => u.id);
          const { data: allClusters } = await supabase
            .from('clusters')
            .select('*')
            .in('upload_id', uploadIds)
            .order('created_at', { ascending: false })
            .limit(50);

          if (allClusters) {
            data.clusters = allClusters;
          }
        }
        
        setAnalytics(data);
      }
      
      setLoading(false);
    } catch (error) {
      console.error('Error fetching analytics:', error);
      setLoading(false);
    }
  };

  const toggleCluster = async (clusterId: number) => {
    if (expandedClusters.has(clusterId)) {
      // Collapse
      const newExpanded = new Set(expandedClusters);
      newExpanded.delete(clusterId);
      setExpandedClusters(newExpanded);
    } else {
      // Expand - fetch details if not already loaded
      if (!clusterDetails.has(clusterId)) {
        try {
          const { data: { session } } = await supabase.auth.getSession();
          if (session) {
            apiClient.setToken(session.access_token);
            const details = await apiClient.getCluster(clusterId);
            setClusterDetails(new Map(clusterDetails.set(clusterId, details)));
          }
        } catch (error) {
          console.error('Error fetching cluster details:', error);
        }
      }
      const newExpanded = new Set(expandedClusters);
      newExpanded.add(clusterId);
      setExpandedClusters(newExpanded);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <div className="animate-spin w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full mx-auto mb-4"></div>
          <p className="text-neutral-400">Loading analytics...</p>
        </div>
      </div>
    );
  }

  if (!analytics) {
    return (
      <div className="text-center text-neutral-400 py-20">
        No analytics data available. Upload some reviews to get started!
      </div>
    );
  }

  const { user_statistics, severity_distribution, status_distribution, recent_activity } = analytics;

  // Calculate resolution rate
  const resolutionRate = user_statistics.total_issues_found > 0
    ? Math.round((user_statistics.total_issues_resolved / user_statistics.total_issues_found) * 100)
    : 0;

  // Calculate total rating reviews
  const totalRatings = 
    user_statistics.rating_1_count +
    user_statistics.rating_2_count +
    user_statistics.rating_3_count +
    user_statistics.rating_4_count +
    user_statistics.rating_5_count;

  // Calculate rating percentages
  const getRatingPercentage = (rating: number) => {
    if (totalRatings === 0) return 0;
    const count = rating === 1 ? user_statistics.rating_1_count :
                  rating === 2 ? user_statistics.rating_2_count :
                  rating === 3 ? user_statistics.rating_3_count :
                  rating === 4 ? user_statistics.rating_4_count :
                  user_statistics.rating_5_count;
    return (count / totalRatings) * 100;
  };

  const getRatingCount = (rating: number) => {
    return rating === 1 ? user_statistics.rating_1_count :
           rating === 2 ? user_statistics.rating_2_count :
           rating === 3 ? user_statistics.rating_3_count :
           rating === 4 ? user_statistics.rating_4_count :
           user_statistics.rating_5_count;
  };

  // Calculate total issues by severity
  const totalSeverity = 
    severity_distribution.critical +
    severity_distribution.high +
    severity_distribution.medium +
    severity_distribution.low;

  return (
    <div className="space-y-8 pb-12">
      {/* Page Header with Upload Info */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-4xl font-bold text-white mb-2 bg-gradient-to-r from-white to-neutral-400 bg-clip-text text-transparent">
              Analytics Dashboard
            </h1>
            <p className="text-neutral-400">
              {uploadId
                ? (
                  <span className="flex items-center gap-2">
                    <span className="font-semibold text-white">
                      {analytics?.upload_data?.filename
                        ? analytics.upload_data.filename.replace(/\.csv$/i, '')
                        : `Upload #${uploadId}`}
                    </span>
                    <span className="text-neutral-600">•</span>
                    <span>{user_statistics.total_reviews_analyzed.toLocaleString()} reviews processed</span>
                    {typeof analytics?.upload_data?.processing_time_seconds === 'number' && (
                      <>
                        <span className="text-neutral-600">•</span>
                        <span className="flex items-center gap-1 text-neutral-400">
                          <Clock className="w-3.5 h-3.5" />
                          Analyzed in {formatDuration(analytics.upload_data.processing_time_seconds)}
                        </span>
                      </>
                    )}
                  </span>
                )
                : "Comprehensive insights and trends from all your reviews"
              }
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Export Buttons */}
            <motion.button
              onClick={exportToCSV}
              disabled={!analytics || exportingReport !== null}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500/20 to-green-500/20 border border-emerald-500/30 hover:border-emerald-500/50 transition-all group disabled:opacity-50 disabled:cursor-not-allowed"
              whileHover={{ scale: analytics ? 1.02 : 1 }}
              whileTap={{ scale: analytics ? 0.98 : 1 }}
            >
              {exportingReport === "csv" ? (
                <Loader2 className="w-4 h-4 text-emerald-400 animate-spin" />
              ) : (
                <FileSpreadsheet className="w-4 h-4 text-emerald-400 group-hover:text-emerald-300 transition-colors" />
              )}
              <span className="text-sm font-semibold text-white">{exportingReport === "csv" ? "Exporting…" : "Export CSV"}</span>
            </motion.button>

            <motion.button
              onClick={exportToPDF}
              disabled={!analytics || exportingReport !== null}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-blue-500/20 to-indigo-500/20 border border-blue-500/30 hover:border-blue-500/50 transition-all group disabled:opacity-50 disabled:cursor-not-allowed"
              whileHover={{ scale: analytics ? 1.02 : 1 }}
              whileTap={{ scale: analytics ? 0.98 : 1 }}
            >
              {exportingReport === "pdf" ? (
                <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
              ) : (
                <Download className="w-4 h-4 text-blue-400 group-hover:text-blue-300 transition-colors" />
              )}
              <span className="text-sm font-semibold text-white">{exportingReport === "pdf" ? "Exporting…" : "Export PDF"}</span>
            </motion.button>

            {/* AI Debug Center Button */}
            <motion.button
              onClick={() => router.push(uploadId ? `/ai-debug?upload_id=${uploadId}` : '/ai-debug')}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-orange-500/20 to-purple-500/20 border border-orange-500/30 hover:border-orange-500/50 transition-all group"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <Sparkles className="w-4 h-4 text-orange-400 group-hover:text-orange-300 transition-colors" />
              <span className="text-sm font-semibold text-white">AI Debug Center</span>
              <ArrowRight className="w-4 h-4 text-orange-400 group-hover:translate-x-0.5 transition-transform" />
            </motion.button>
            
            {uploadId && (
              <motion.div 
                className="px-4 py-2 rounded-xl bg-gradient-to-r from-orange-500/20 to-red-500/20 border border-orange-500/30"
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ delay: 0.2 }}
              >
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-orange-500 animate-pulse"></div>
                  <span className="text-sm font-medium text-orange-300">Latest Upload</span>
                </div>
              </motion.div>
            )}
          </div>
        </div>
      </motion.div>

      {/* Key Metrics - 4 Column Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1, duration: 0.4 }}
          whileHover={{ y: -4, transition: { duration: 0.2 } }}
        >
          <SpotlightCard className="p-6 relative overflow-hidden h-full">
            <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-blue-500/10 to-transparent rounded-full blur-2xl"></div>
            <div className="relative">
              <div className="flex items-start justify-between mb-4">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500/20 to-cyan-500/20 border border-blue-500/20 flex items-center justify-center">
                  <BarChart3 className="w-6 h-6 text-blue-400" />
                </div>
                <div className="text-right">
                  <p className="text-xs text-neutral-500 uppercase tracking-wider">Total</p>
                </div>
              </div>
              <p className="text-sm text-neutral-400 mb-2">Reviews Analyzed</p>
              <p className="text-4xl font-black text-white mb-1">
                {user_statistics.total_reviews_analyzed.toLocaleString()}
              </p>
              <div className="flex items-center gap-2 mt-3">
                <div className="flex-1 h-1 rounded-full bg-blue-500/20">
                  <motion.div 
                    className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-500"
                    initial={{ width: 0 }}
                    animate={{ width: "100%" }}
                    transition={{ delay: 0.3, duration: 0.8, ease: "easeOut" }}
                  ></motion.div>
                </div>
                <span className="text-xs text-blue-400 font-medium">100%</span>
              </div>
            </div>
          </SpotlightCard>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15, duration: 0.4 }}
          whileHover={{ y: -4, transition: { duration: 0.2 } }}
        >
          <SpotlightCard className="p-6 relative overflow-hidden h-full">
            <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-orange-500/10 to-transparent rounded-full blur-2xl"></div>
            <div className="relative">
              <div className="flex items-start justify-between mb-4">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-orange-500/20 to-red-500/20 border border-orange-500/20 flex items-center justify-center">
                  <AlertTriangle className="w-6 h-6 text-orange-400" />
                </div>
                <div className="text-right">
                  <p className="text-xs text-orange-400 uppercase tracking-wider font-bold">Issues</p>
                </div>
              </div>
              <p className="text-sm text-neutral-400 mb-2">Issues Detected</p>
              <motion.p 
                className="text-4xl font-black text-white mb-1"
                initial={{ opacity: 0, scale: 0.5 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.4, duration: 0.5, type: "spring" }}
              >
                {user_statistics.total_issues_found}
              </motion.p>
              <div className="flex items-center gap-2 mt-3">
                <Flame className="w-3 h-3 text-orange-400" />
                <span className="text-xs text-neutral-500">
                  {severity_distribution.critical} critical • {severity_distribution.high} high
                </span>
              </div>
            </div>
          </SpotlightCard>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.4 }}
          whileHover={{ y: -4, transition: { duration: 0.2 } }}
        >
          <SpotlightCard className="p-6 relative overflow-hidden h-full">
            <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-amber-500/10 to-transparent rounded-full blur-2xl"></div>
            <div className="relative">
              <div className="flex items-start justify-between mb-4">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-amber-500/20 to-orange-500/20 border border-amber-500/20 flex items-center justify-center">
                  <Target className="w-6 h-6 text-amber-400" />
                </div>
                <div className="text-right">
                  <p className="text-xs text-amber-400 uppercase tracking-wider font-bold">
                    {analytics?.upload_data?.total_reviews && analytics?.upload_data?.filtered_noise 
                      ? Math.round((analytics.upload_data.filtered_noise / analytics.upload_data.total_reviews) * 100)
                      : 0}%
                  </p>
                </div>
              </div>
              <p className="text-sm text-neutral-400 mb-2">Noise Filtered</p>
              <motion.p 
                className="text-4xl font-black text-white mb-1"
                initial={{ opacity: 0, scale: 0.5 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.45, duration: 0.5, type: "spring" }}
              >
                {analytics?.upload_data?.filtered_noise || 0}
              </motion.p>
              <div className="flex items-center gap-2 mt-3">
                <span className="text-xs text-neutral-500">
                  {analytics?.upload_data?.total_reviews && analytics?.upload_data?.filtered_noise
                    ? `${analytics.upload_data.total_reviews - analytics.upload_data.filtered_noise} kept for analysis`
                    : 'Low-quality reviews removed'
                  }
                </span>
              </div>
            </div>
          </SpotlightCard>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25, duration: 0.4 }}
          whileHover={{ y: -4, transition: { duration: 0.2 } }}
        >
          <SpotlightCard className="p-6 relative overflow-hidden h-full">
            <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-purple-500/10 to-transparent rounded-full blur-2xl"></div>
            <div className="relative">
              <div className="flex items-start justify-between mb-4">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 border border-purple-500/20 flex items-center justify-center">
                  <Activity className="w-6 h-6 text-purple-400" />
                </div>
                <div className="text-right">
                  <p className="text-xs text-neutral-500 uppercase tracking-wider">Total</p>
                </div>
              </div>
              <p className="text-sm text-neutral-400 mb-2">Clusters Created</p>
              <motion.p 
                className="text-4xl font-black text-white mb-1"
                initial={{ opacity: 0, scale: 0.5 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.5, duration: 0.5, type: "spring" }}
              >
                {analytics?.clusters?.length || 0}
              </motion.p>
              <div className="flex items-center gap-2 mt-3">
                <span className="text-xs text-neutral-500">AI-grouped review patterns</span>
              </div>
            </div>
          </SpotlightCard>
        </motion.div>
      </div>

      {/* â”€â”€ Row 1: #1 User Complaint â€” full width â”€â”€ */}
      {(() => {
        const clusters = analytics.clusters || [];
        const totalReviews = clusters.reduce((s, c) => s + (c.review_count || 0), 0);

        const cleanTitle = (t: string) =>
          t.replace(/^\[(CRITICAL|HIGH|MEDIUM|LOW)\]\s*(Issue:\s*)?/i, '')
           .replace(/^Issue:\s*/i, '')
           .trim();

        const severityMeta: Record<string, { label: string; color: string; bg: string; border: string; dot: string; textBg: string }> = {
          critical: { label: 'CRITICAL', color: 'text-red-400',     bg: 'bg-red-500/10',    border: 'border-red-500/25',    dot: 'bg-red-500',    textBg: 'bg-red-500/15' },
          high:     { label: 'HIGH',     color: 'text-orange-400',  bg: 'bg-orange-500/10', border: 'border-orange-500/25', dot: 'bg-orange-500', textBg: 'bg-orange-500/15' },
          medium:   { label: 'MEDIUM',   color: 'text-yellow-400',  bg: 'bg-yellow-500/10', border: 'border-yellow-500/25', dot: 'bg-yellow-500', textBg: 'bg-yellow-500/15' },
          low:      { label: 'LOW',      color: 'text-blue-400',    bg: 'bg-blue-500/10',   border: 'border-blue-500/25',   dot: 'bg-blue-500',   textBg: 'bg-blue-500/15' },
        };
        const statusEmoji: Record<string, string> = { fresh_roast: '🔥', assigned: '👤', in_progress: '🔄', resolved: '✅', wont_fix: '🚫' };
        const statusLabel: Record<string, string> = { fresh_roast: 'Fresh Roast', assigned: 'Assigned', in_progress: 'In Progress', resolved: 'Resolved', wont_fix: "Won't Fix" };

        if (clusters.length === 0 || totalReviews === 0) return null;

        const sorted = [...clusters].sort((a, b) => (b.review_count || 0) - (a.review_count || 0));
        const top = sorted[0];
        const runners = sorted.slice(1, 5); // exactly 4 runner-ups â†’ clean 4-col row
        const topMeta = severityMeta[top.severity] ?? severityMeta.low;
        const topPct = Math.round(((top.review_count || 0) / totalReviews) * 100);

        // A LOW-severity "issue" is often just praise the pipeline kept as a
        // cluster (e.g. "Nice app, excellent...") -- calling that a
        // "complaint" is actively wrong, not just imprecise. Detect it from
        // the title's own language instead of assuming severity == complaint.
        const positiveWords = /\b(nice|good|great|excellent|love|like|awesome|amazing|perfect|best|fantastic|super|wonderful|fun|enjoy|enjoying|cool|helpful|useful|satisfied|happy)\b/i;
        const negativeWords = /\b(bad|crash|broken|bug|issue|problem|fail|hate|worst|terrible|slow|annoying|error|stuck|lag|freeze|glitch)\b/i;
        const topTitleClean = cleanTitle(top.title);
        const isTopPositive =
          top.severity === 'low' &&
          positiveWords.test(topTitleClean) &&
          !negativeWords.test(topTitleClean);

        const topHeading = isTopPositive ? '#1 Top Signal' : '#1 User Complaint';
        const topIconBg = isTopPositive
          ? 'from-emerald-500/20 to-green-500/20 border-emerald-500/20'
          : 'from-red-500/20 to-orange-500/20 border-red-500/20';
        const topIconColor = isTopPositive ? 'text-emerald-400' : 'text-red-400';

        return (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.5 }}
          >
            <SpotlightCard className="p-6">
              {/* Card header */}
              <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-3">
                  <div className={`w-9 h-9 rounded-lg bg-gradient-to-br ${topIconBg} border flex items-center justify-center`}>
                    <Flame className={`w-4 h-4 ${topIconColor}`} />
                  </div>
                  <div>
                    <h3 className="font-bold text-white">{topHeading}</h3>
                    <p className="text-xs text-neutral-500">Loudest cluster by review volume - {totalReviews.toLocaleString()} total reviews</p>
                  </div>
                </div>
                <span className={`text-xs font-black px-2.5 py-1 rounded-full border ${topMeta.color} ${topMeta.textBg} ${topMeta.border}`}>
                  {topMeta.label}
                </span>
              </div>

              {/* Top complaint â€” horizontal split */}
              <motion.div
                className={`rounded-xl border ${topMeta.border} ${topMeta.bg} mb-5`}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
              >
                <div className="flex flex-col lg:flex-row lg:items-center gap-4 p-5">
                  {/* Title */}
                  <p className="flex-1 text-lg font-bold text-white leading-snug">
                    &ldquo;{cleanTitle(top.title)}&rdquo;
                  </p>
                  {/* Stats */}
                  <div className="flex items-center gap-6 flex-shrink-0">
                    <div className="text-center">
                      <p className={`text-2xl font-black ${topMeta.color}`}>{topPct}%</p>
                      <p className="text-xs text-neutral-500">of total</p>
                    </div>
                    <div className="text-center">
                      <p className="text-2xl font-black text-white">{(top.review_count || 0).toLocaleString()}</p>
                      <p className="text-xs text-neutral-500">reviews</p>
                    </div>
                    <div className="text-center">
                      <p className="text-lg">{statusEmoji[top.status] ?? 'â“'}</p>
                      <p className="text-xs text-neutral-500">{statusLabel[top.status] ?? top.status}</p>
                    </div>
                  </div>
                </div>
                {/* Progress bar */}
                <div className="px-5 pb-4">
                  <div className="h-2 rounded-full bg-white/5">
                    <motion.div
                      className={`h-full rounded-full ${topMeta.dot}`}
                      initial={{ width: 0 }}
                      animate={{ width: `${topPct}%` }}
                      transition={{ delay: 0.4, duration: 0.9, ease: 'easeOut' }}
                    />
                  </div>
                </div>
              </motion.div>

              {/* 4 runner-ups in a single even row */}
              <div>
                <p className="text-xs text-neutral-600 uppercase tracking-wider mb-3">Next biggest</p>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                  {runners.map((c, i) => {
                    const meta = severityMeta[c.severity] ?? severityMeta.low;
                    const pct = Math.round(((c.review_count || 0) / totalReviews) * 100);
                    const relPct = Math.round(((c.review_count || 0) / (top.review_count || 1)) * 100);
                    return (
                      <motion.div
                        key={c.id}
                        className={`rounded-xl p-3.5 border ${meta.border} ${meta.bg} flex flex-col gap-2`}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.35 + i * 0.06 }}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-neutral-600 font-bold">#{i + 2}</span>
                          <span className={`text-[10px] font-black px-1.5 py-0.5 rounded border ${meta.color} ${meta.textBg} ${meta.border}`}>{meta.label}</span>
                        </div>
                        <p className="text-xs text-neutral-200 leading-relaxed line-clamp-3 flex-1">{cleanTitle(c.title)}</p>
                        <div>
                          <div className="flex justify-between text-[10px] text-neutral-600 mb-1">
                            <span>{(c.review_count || 0).toLocaleString()} reviews</span>
                            <span>{pct}%</span>
                          </div>
                          <div className="h-1 rounded-full bg-white/5">
                            <motion.div
                              className={`h-full rounded-full ${meta.dot}`}
                              initial={{ width: 0 }}
                              animate={{ width: `${relPct}%` }}
                              transition={{ delay: 0.45 + i * 0.06, duration: 0.6 }}
                            />
                          </div>
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
              </div>
            </SpotlightCard>
          </motion.div>
        );
      })()}

      {/* â”€â”€ Row 2: Severity Distribution + Issue Categories â€” equal 2-col â”€â”€ */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Severity Distribution */}
        <motion.div
          initial={{ opacity: 0, x: -16 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.38, duration: 0.5 }}
        >
          <SpotlightCard className="p-6 h-full">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-red-500/20 to-orange-500/20 border border-red-500/20 flex items-center justify-center">
                <Flame className="w-4 h-4 text-red-400" />
              </div>
              <div>
                <h3 className="font-bold text-white">Severity Distribution</h3>
                <p className="text-xs text-neutral-500">{totalSeverity} total issues categorized</p>
              </div>
            </div>

            {totalSeverity > 0 ? (() => {
              const maxCount = Math.max(
                severity_distribution.critical,
                severity_distribution.high,
                severity_distribution.medium,
                severity_distribution.low
              );
              const rows = [
                { key: 'critical', label: 'Critical', count: severity_distribution.critical, color: 'text-red-400',    bar: 'from-red-600 to-red-400',       dot: 'bg-red-500',    delay: 0.4 },
                { key: 'high',     label: 'High',     count: severity_distribution.high,     color: 'text-orange-400', bar: 'from-orange-600 to-orange-400', dot: 'bg-orange-500', delay: 0.48 },
                { key: 'medium',   label: 'Medium',   count: severity_distribution.medium,   color: 'text-yellow-400', bar: 'from-yellow-600 to-yellow-400', dot: 'bg-yellow-500', delay: 0.56 },
                { key: 'low',      label: 'Low',      count: severity_distribution.low,      color: 'text-blue-400',   bar: 'from-blue-600 to-blue-400',     dot: 'bg-blue-500',   delay: 0.64 },
              ];
              return (
                <div className="space-y-4">
                  {rows.map(r => (
                    <div key={r.key}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <div className={`w-2.5 h-2.5 rounded-full ${r.dot}`} />
                          <span className={`text-sm font-bold ${r.color} uppercase tracking-wide`}>{r.label}</span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-base font-black text-white">{r.count}</span>
                          <span className={`text-sm font-bold ${r.color} w-10 text-right`}>
                            {Math.round((r.count / totalSeverity) * 100)}%
                          </span>
                        </div>
                      </div>
                      <div className="h-2.5 rounded-full bg-white/5 overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${(r.count / maxCount) * 100}%` }}
                          transition={{ duration: 0.75, delay: r.delay }}
                          className={`h-full bg-gradient-to-r ${r.bar} rounded-full`}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              );
            })() : (
              <p className="text-neutral-500 text-center py-10 text-sm">No data</p>
            )}
          </SpotlightCard>
        </motion.div>

        {/* Issue Categories */}
        <motion.div
          initial={{ opacity: 0, x: 16 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.42, duration: 0.5 }}
        >
          <SpotlightCard className="p-6 h-full">
            {(() => {
              const clusters = analytics.clusters || [];
              const categoryRules: { label: string; icon: string; color: string; bar: string; keywords: string[] }[] = [
                { label: 'Crashes & Errors',   icon: '💥', color: 'text-red-400',     bar: 'bg-red-500',     keywords: ['crash','crashing','not open','force close','freeze','stuck','black screen','not working','broken'] },
                { label: 'Performance',         icon: '🐢', color: 'text-orange-400',  bar: 'bg-orange-500',  keywords: ['lag','slow','loading','battery','hang','performance','takes long','drains'] },
                { label: 'Ads',                 icon: '📢', color: 'text-yellow-400',  bar: 'bg-yellow-500',  keywords: ['ad','ads','advertisement','popup','pop-up','too many ads','annoying ad','banner'] },
                { label: 'Login / Account',     icon: '🔑', color: 'text-cyan-400',    bar: 'bg-cyan-500',    keywords: ['login','sign in','sign out','account','password','otp','verify','logout','session'] },
                { label: 'Payments',            icon: '💸', color: 'text-emerald-400', bar: 'bg-emerald-500', keywords: ['pay','paid','purchase','subscription','refund','charge','money','buy','coin','gem','booster','reward'] },
                { label: 'Gameplay / Features', icon: '🎮', color: 'text-purple-400',  bar: 'bg-purple-500',  keywords: ['level','game','play','lives','score','feature','update','new','missing','removed'] },
                { label: 'UI / Design',         icon: '🎨', color: 'text-pink-400',    bar: 'bg-pink-500',    keywords: ['ui','design','button','screen','dark mode','interface','look','layout','ugly','beautiful'] },
              ];
              const categoryCounts = categoryRules.map(cat => {
                let count = 0;
                clusters.forEach(c => {
                  if (cat.keywords.some(kw => (c.title || '').toLowerCase().includes(kw)))
                    count += (c.review_count || 0);
                });
                return { ...cat, count };
              }).filter(c => c.count > 0).sort((a, b) => b.count - a.count);

              const maxCat = categoryCounts[0]?.count || 1;

              return (
                <div>
                  <div className="flex items-center gap-3 mb-5">
                    <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-purple-500/20 to-pink-500/20 border border-purple-500/20 flex items-center justify-center">
                      <PieChart className="w-4 h-4 text-purple-400" />
                    </div>
                    <div>
                      <h3 className="font-bold text-white">Issue Categories</h3>
                      <p className="text-xs text-neutral-500">What type of problems dominate</p>
                    </div>
                  </div>

                  {categoryCounts.length > 0 ? (
                    <div className="space-y-4">
                      {categoryCounts.slice(0, 5).map((cat, i) => (
                        <motion.div
                          key={cat.label}
                          initial={{ opacity: 0, x: 10 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: 0.45 + i * 0.07 }}
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <span className="text-base leading-none">{cat.icon}</span>
                              <span className={`text-sm font-bold ${cat.color}`}>{cat.label}</span>
                            </div>
                            <span className="text-xs text-neutral-500">{cat.count.toLocaleString()} reviews</span>
                          </div>
                          <div className="h-2.5 rounded-full bg-white/5">
                            <motion.div
                              className={`h-full rounded-full ${cat.bar}`}
                              initial={{ width: 0 }}
                              animate={{ width: `${(cat.count / maxCat) * 100}%` }}
                              transition={{ delay: 0.5 + i * 0.08, duration: 0.75 }}
                            />
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-neutral-500 text-center py-10 text-sm">No categories matched</p>
                  )}
                </div>
              );
            })()}
          </SpotlightCard>
        </motion.div>
      </div>

      {/* â”€â”€ Cluster List: Spike Detection + Fix Regression + Ticket Export â”€â”€ */}
      {analytics.clusters && analytics.clusters.length > 0 && (() => {
        // Severity visual config
        type SevCfg = { color: string; bg: string; border: string; hover: string };
        const sevCfg: Record<string, SevCfg> = {
          critical: { color: 'text-red-400',    bg: 'bg-red-500/10',    border: 'border-red-500/20',    hover: 'rgba(239,68,68,0.08)' },
          high:     { color: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/20', hover: 'rgba(249,115,22,0.08)' },
          medium:   { color: 'text-yellow-400', bg: 'bg-yellow-500/10', border: 'border-yellow-500/20', hover: 'rgba(234,179,8,0.08)' },
          low:      { color: 'text-blue-400',   bg: 'bg-blue-500/10',   border: 'border-blue-500/20',   hover: 'rgba(59,130,246,0.08)' },
        };

        // Shared row renderer â€” used for all 4 severity buckets
        const renderRow = (
          cluster: NonNullable<AnalyticsData['clusters']>[number],
          index: number,
          baseDelay: number
        ) => {
          const s = sevCfg[cluster.severity] ?? sevCfg.low;
          const isExpanded = expandedClusters.has(cluster.id);
          const details = clusterDetails.get(cluster.id);
          const isSpiking = spikeIds.has(cluster.id);
          const triage = triageScores.get(cluster.id);
          const isRegression = !!cluster.regression_detected;

          // â”€â”€ User-facing AI badges (same agent data, plain-language framing) â”€â”€
          const meta = cluster.ai_metadata;
          const precedentCount = meta?.similar_issues?.length ?? 0;
          const isRecurring = precedentCount > 0;
          const faithfulness = meta?.eval_scores?.faithfulness;
          const hasTrustSignal = typeof faithfulness === 'number';
          const isWellSupported = hasTrustSignal && faithfulness! >= 0.5;
          const severityAdjusted = !!(
            meta?.suggested_severity &&
            meta.suggested_severity.toLowerCase() !== cluster.severity.toLowerCase()
          );

          return (
            <motion.div
              key={cluster.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: baseDelay + index * 0.05, duration: 0.3 }}
              className={`rounded-xl ${s.bg} border ${s.border} overflow-hidden`}
            >
              {/* Row: accordion toggle (flex-1) + export ticket button */}
              <div className="flex items-stretch">
                <motion.button
                  whileHover={{ backgroundColor: s.hover }}
                  onClick={() => toggleCluster(cluster.id)}
                  className="flex-1 p-4 transition-colors text-left min-w-0"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      {/* Spike / Regression / Recurring / trust / severity-correction badges */}
                      {(isSpiking || isRegression || isRecurring || hasTrustSignal || severityAdjusted) && (
                        <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
                          {isSpiking && (
                            <span className="inline-flex items-center gap-1 text-[9px] font-black px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30 tracking-wide">
                              <Zap className="w-2.5 h-2.5" />SPIKING
                            </span>
                          )}
                          {isRegression && (
                            <span
                              className="inline-flex items-center gap-1 text-[9px] font-black px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-400 border border-purple-500/30 tracking-wide cursor-help"
                              title={[
                                cluster.regression_of_title
                                  ? `The fix didn't hold. Previously resolved as: "${cluster.regression_of_title}"`
                                  : 'This issue was previously resolved and has re-appeared',
                                typeof cluster.regression_confidence === 'number'
                                  ? `Match confidence: ${(cluster.regression_confidence * 100).toFixed(0)}%`
                                  : null,
                                cluster.regression_match_method === 'semantic'
                                  ? 'Matched by meaning (different wording, same underlying bug)'
                                  : cluster.regression_match_method === 'keyword+semantic'
                                    ? 'Matched by both wording and meaning'
                                    : cluster.regression_match_method === 'keyword'
                                      ? 'Matched by shared wording'
                                      : null,
                              ].filter(Boolean).join('\n')}
                            >
                              <RotateCcw className="w-2.5 h-2.5" />
                              FIX DIDN&apos;T HOLD
                              {typeof cluster.regression_confidence === 'number' && (
                                <span className="opacity-70">{(cluster.regression_confidence * 100).toFixed(0)}%</span>
                              )}
                              <HelpCircle className="w-2.5 h-2.5 opacity-60" />
                            </span>
                          )}
                          {isRecurring && (
                            <span
                              className="inline-flex items-center gap-1 text-[9px] font-black px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 tracking-wide cursor-help"
                              title={meta!.similar_issues.map(s => `"${s.title}" (${s.severity})`).join('\n')}
                            >
                              🔁 RECURRING - seen {precedentCount}x before
                              <HelpCircle className="w-2.5 h-2.5 opacity-60" />
                            </span>
                          )}
                          {hasTrustSignal && (
                            isWellSupported ? (
                              <span className="inline-flex items-center gap-1 text-[9px] font-black px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 tracking-wide">
                                ✓ WELL-SUPPORTED BY EVIDENCE
                              </span>
                            ) : (
                              <span
                                className="inline-flex items-center gap-1 text-[9px] font-black px-1.5 py-0.5 rounded bg-yellow-500/15 text-yellow-400 border border-yellow-500/30 tracking-wide cursor-help"
                                title="The AI's explanation goes beyond what's directly stated in the reviews -- treat this as a lead, not a confirmed diagnosis."
                              >
                                ! SPECULATIVE - VERIFY MANUALLY
                                <HelpCircle className="w-2.5 h-2.5 opacity-60" />
                              </span>
                            )
                          )}
                          {severityAdjusted && (
                            <span
                              className="inline-flex items-center gap-1 text-[9px] font-black px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30 tracking-wide cursor-help"
                              title={meta!.severity_reason}
                            >
                              SEVERITY ADJUSTED: {cluster.severity.toUpperCase()} {'->'} {meta!.suggested_severity}
                              <HelpCircle className="w-2.5 h-2.5 opacity-60" />
                            </span>
                          )}
                        </div>
                      )}
                      <p className="text-sm text-white font-medium leading-snug">{cluster.title}</p>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {triage && (
                        <span
                          className="inline-flex items-center gap-1 text-[10px] font-black px-2 py-0.5 rounded-full bg-white/5 text-neutral-300 border border-white/10 cursor-help whitespace-nowrap"
                          title={[
                            `Priority score: ${triage.score}`,
                            '',
                            'Fused from:',
                            `  severity weight   ${triage.breakdown.severity_weight ?? '—'}`,
                            `  AI faithfulness   ${triage.breakdown.faithfulness ?? '—'}`,
                            `  regression boost  ${triage.breakdown.regression_boost ?? 0}`,
                            `  review volume     ${triage.breakdown.velocity ?? '—'}`,
                          ].join('\n')}
                        >
                          ⚡ {triage.score}
                        </span>
                      )}
                      <span className={`text-xs ${s.color} font-medium whitespace-nowrap`}>
                        {cluster.review_count} review{cluster.review_count !== 1 ? 's' : ''}
                      </span>
                      {isExpanded
                        ? <ChevronUp className={`w-4 h-4 ${s.color}`} />
                        : <ChevronDown className={`w-4 h-4 ${s.color}`} />}
                    </div>
                  </div>
                </motion.button>

                {/* Mark resolved / reopen -- the fix-verification loop's real trigger */}
                <button
                  onClick={(e) => { e.stopPropagation(); toggleResolved(cluster); }}
                  disabled={resolvingId === cluster.id}
                  className={`border-l ${s.border} px-3 flex items-center transition-colors disabled:opacity-50 ${
                    cluster.status === 'resolved' ? 'text-emerald-400 hover:text-emerald-300' : 'text-neutral-600 hover:text-neutral-300'
                  }`}
                  title={cluster.status === 'resolved' ? 'Reopen this issue' : 'Mark as resolved'}
                >
                  {resolvingId === cluster.id
                    ? <Loader2 className="w-3.5 h-3.5 animate-spin text-neutral-400" />
                    : <CheckCircle2 className="w-3.5 h-3.5" />
                  }
                </button>

                {/* Export to ticket â€” separate from the accordion toggle */}
                <button
                  onClick={(e) => { e.stopPropagation(); openExport(cluster); }}
                  className={`border-l ${s.border} px-3 flex items-center text-neutral-600 hover:text-neutral-300 transition-colors`}
                  title="Export as GitHub / Linear ticket"
                >
                  {loadingExportId === cluster.id
                    ? <Loader2 className="w-3.5 h-3.5 animate-spin text-neutral-400" />
                    : <Ticket className="w-3.5 h-3.5" />
                  }
                </button>
              </div>

              {/* Accordion — AI agent analysis + sample reviews */}
              <AnimatePresence>
                {isExpanded && details && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.25, ease: 'easeInOut' }}
                    className={`border-t ${s.border}`}
                  >
                    {details.ai_metadata && (
                      <AgentAnalysisPanel metadata={details.ai_metadata} accentColor={s.color} />
                    )}

                    {/* Release bisect — only when the CSV actually carried an
                        app-version column (most don't, so this is absent
                        rather than faked). */}
                    {details.version_bisect && (
                      <div className="px-4 py-3 bg-black/20 border-b border-white/5">
                        <p className={`text-xs ${s.color} font-semibold uppercase tracking-wider mb-2`}>
                          Release bisect
                        </p>
                        <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs">
                          {details.version_bisect.earliest_version && (
                            <span className="text-neutral-300">
                              First seen in{' '}
                              <span className="font-mono font-bold text-white">
                                {details.version_bisect.earliest_version}
                              </span>
                            </span>
                          )}
                          <span className="text-neutral-400">
                            Most reports on{' '}
                            <span className="font-mono font-bold text-neutral-200">
                              {details.version_bisect.most_common_version}
                            </span>
                          </span>
                          <span className="text-neutral-600">
                            {details.version_bisect.distinct_versions} version
                            {details.version_bisect.distinct_versions !== 1 ? 's' : ''} affected
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Repro test stub — turns the RCA's repro steps into a
                        runnable Playwright skeleton on demand. */}
                    <div className="px-4 py-3 bg-black/20 border-b border-white/5">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className={`text-xs ${s.color} font-semibold uppercase tracking-wider`}>
                            Repro test stub
                          </p>
                          <p className="text-[11px] text-neutral-600 mt-0.5">
                            Generates a Playwright skeleton from this issue&apos;s repro steps
                          </p>
                        </div>
                        <button
                          onClick={(e) => { e.stopPropagation(); generateStub(cluster.id); }}
                          disabled={loadingStubId === cluster.id}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-[11px] font-semibold text-neutral-200 hover:bg-white/10 transition-colors disabled:opacity-50 flex-shrink-0"
                        >
                          {loadingStubId === cluster.id
                            ? <><Loader2 className="w-3 h-3 animate-spin" />Generating…</>
                            : <><FlaskConical className="w-3 h-3" />{testStubs.has(cluster.id) ? 'Regenerate' : 'Generate test'}</>}
                        </button>
                      </div>

                      {stubError.get(cluster.id) && (
                        <p className="text-[11px] text-red-400 mt-2">{stubError.get(cluster.id)}</p>
                      )}

                      {testStubs.has(cluster.id) && (
                        <div className="mt-3">
                          <div className="flex items-center justify-end mb-1.5">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                navigator.clipboard.writeText(testStubs.get(cluster.id) || '');
                              }}
                              className="text-[10px] text-neutral-500 hover:text-neutral-300 transition-colors"
                            >
                              Copy
                            </button>
                          </div>
                          <pre className="p-3 rounded-lg bg-black/50 border border-white/10 text-[11px] text-neutral-300 overflow-x-auto whitespace-pre-wrap font-mono leading-relaxed max-h-72 overflow-y-auto">
                            {testStubs.get(cluster.id)}
                          </pre>
                        </div>
                      )}
                    </div>
                    {details.sample_reviews && (
                    <div className="p-4 space-y-3 bg-black/20">
                      <p className={`text-xs ${s.color} font-semibold uppercase tracking-wider`}>
                        Sample Reviews ({details.sample_reviews.length})
                      </p>
                      {details.sample_reviews.map((review, idx) => (
                        <div key={idx} className={`p-3 rounded-md ${s.bg} border ${s.border}`}>
                          <div className="flex items-start gap-2 mb-2">
                            {review.rating && (
                              <div className="flex items-center gap-1">
                                {Array.from({ length: 5 }).map((_, i) => (
                                  <Star key={i} className={`w-3 h-3 ${i < review.rating! ? 'fill-yellow-500 text-yellow-500' : 'text-neutral-700'}`} />
                                ))}
                              </div>
                            )}
                            {review.device && <span className="text-xs text-neutral-500">• {review.device}</span>}
                            {review.version && <span className="text-xs text-neutral-500">• v{review.version}</span>}
                          </div>
                          <p className="text-sm text-neutral-300 leading-relaxed whitespace-pre-wrap">{review.content}</p>
                        </div>
                      ))}
                    </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          );
        };

        const severities = [
          { key: 'critical', label: 'Critical', dotCls: 'bg-red-500 shadow-lg shadow-red-500/50',    textCls: 'text-red-400',    delay: 0.6  },
          { key: 'high',     label: 'High',     dotCls: 'bg-orange-500 shadow-lg shadow-orange-500/50', textCls: 'text-orange-400', delay: 0.65 },
          { key: 'medium',   label: 'Medium',   dotCls: 'bg-yellow-500 shadow-lg shadow-yellow-500/50', textCls: 'text-yellow-400', delay: 0.7  },
          { key: 'low',      label: 'Low',      dotCls: 'bg-blue-500 shadow-lg shadow-blue-500/50',   textCls: 'text-blue-400',   delay: 0.75 },
        ];

        const totalSpiking = spikeIds.size;
        const totalRegressions = analytics.clusters.filter(c => c.regression_detected).length;

        return (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.45, duration: 0.5 }}
          >
            <SpotlightCard className="p-8">
              {/* Card header */}
              <div className="flex flex-wrap items-start justify-between gap-4 mb-8">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 border border-purple-500/20 flex items-center justify-center">
                    <Layers className="w-6 h-6 text-purple-400" />
                  </div>
                  <div>
                    <h3 className="text-xl font-bold text-white">Issue Clusters Breakdown</h3>
                    <p className="text-sm text-neutral-400">
                      {analytics.clusters.length} clusters identified
                      {uploadId && ' from this upload'}
                    </p>
                    {aiEnrichmentPending && (
                      <p className="flex items-center gap-1.5 text-xs text-purple-300 mt-1.5">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        AI analysis still running for top issues — recurring/well-supported badges and agent details will appear here automatically, no need to refresh
                      </p>
                    )}
                    {aiEnrichmentGaveUp && (
                      <p className="text-xs text-neutral-500 mt-1.5">
                        AI analysis is taking longer than usual (API rate limit) — reload the page in a bit to check again
                      </p>
                    )}
                  </div>
                </div>

                {/* Signal summary badges + export hint */}
                <div className="flex flex-wrap items-center gap-2">
                  {/* Sort mode: severity buckets vs fused priority ranking */}
                  {triageScores.size > 0 && (
                    <div className="flex items-center rounded-full bg-white/5 border border-white/10 p-0.5 mr-1">
                      <button
                        onClick={() => setSortMode('severity')}
                        className={`px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide transition-colors ${
                          sortMode === 'severity' ? 'bg-white/10 text-white' : 'text-neutral-500 hover:text-neutral-300'
                        }`}
                      >
                        By severity
                      </button>
                      <button
                        onClick={() => setSortMode('triage')}
                        className={`px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide transition-colors ${
                          sortMode === 'triage' ? 'bg-white/10 text-white' : 'text-neutral-500 hover:text-neutral-300'
                        }`}
                        title="One ranked list, scored from severity + AI evidence quality + regression signal + review volume"
                      >
                        ⚡ Fix first
                      </button>
                    </div>
                  )}
                  {totalSpiking > 0 && (
                    <span className="inline-flex items-center gap-1.5 text-xs font-black px-3 py-1.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30">
                      <Zap className="w-3 h-3" />{totalSpiking} SPIKING
                    </span>
                  )}
                  {totalRegressions > 0 && (
                    <span className="inline-flex items-center gap-1.5 text-xs font-black px-3 py-1.5 rounded-full bg-purple-500/15 text-purple-400 border border-purple-500/30">
                      <RotateCcw className="w-3 h-3" />{totalRegressions} REGRESSION{totalRegressions !== 1 ? 'S' : ''}
                    </span>
                  )}
                  <span className="inline-flex items-center gap-1 text-[11px] text-neutral-600">
                    <Ticket className="w-3 h-3" />to export
                  </span>
                </div>
              </div>

              {/* Cross-platform fusion — best-effort: the pipeline has no real
                  platform column, so these are candidates to confirm, not
                  guaranteed matches. */}
              {crossPlatform.length > 0 && (
                <div className="mb-6 p-4 rounded-xl bg-teal-500/5 border border-teal-500/20">
                  <p className="flex items-center gap-2 text-xs font-bold text-teal-300 uppercase tracking-wider mb-2">
                    <Layers className="w-3.5 h-3.5" />
                    Same bug on both platforms?
                  </p>
                  <p className="text-[11px] text-neutral-500 mb-3">
                    These Android and iOS clusters look like one shared issue rather than two client-specific bugs —
                    worth checking before triaging them separately. Platform is inferred from review wording, so
                    confirm before merging.
                  </p>
                  <div className="space-y-2">
                    {crossPlatform.slice(0, 5).map((m) => (
                      <div
                        key={`${m.android_cluster_id}-${m.ios_cluster_id}`}
                        className="flex flex-wrap items-center gap-2 text-xs"
                      >
                        <span className="px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 text-[9px] font-black">ANDROID</span>
                        <span className="text-neutral-300 truncate max-w-[16rem]">{m.android_title}</span>
                        <span className="text-neutral-600">↔</span>
                        <span className="px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300 text-[9px] font-black">IOS</span>
                        <span className="text-neutral-300 truncate max-w-[16rem]">{m.ios_title}</span>
                        <span className="text-neutral-500 text-[10px]">{(m.confidence * 100).toFixed(0)}% similar</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Cluster list — severity buckets, or one flat priority ranking */}
              {sortMode === 'triage' ? (
                <div>
                  <div className="flex items-center gap-2 mb-4">
                    <Zap className="w-3.5 h-3.5 text-white" />
                    <h4 className="text-sm font-bold text-white uppercase tracking-wider">
                      Ranked by priority ({analytics.clusters!.length})
                    </h4>
                  </div>
                  <div className="space-y-3">
                    {[...analytics.clusters!]
                      .sort((a, b) =>
                        (triageScores.get(b.id)?.score ?? -1) - (triageScores.get(a.id)?.score ?? -1)
                      )
                      .map((cluster, idx) => renderRow(cluster, idx, 0.5))}
                  </div>
                </div>
              ) : (
                <div className="space-y-6">
                  {severities.map(({ key, label, dotCls, textCls, delay }) => {
                    const bucket = analytics.clusters!.filter(c => c.severity === key);
                    if (bucket.length === 0) return null;
                    return (
                      <motion.div
                        key={key}
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay, duration: 0.4 }}
                      >
                        <div className="flex items-center gap-2 mb-4">
                          <div className={`w-3 h-3 rounded-full ${dotCls}`} />
                          <h4 className={`text-sm font-bold ${textCls} uppercase tracking-wider`}>
                            {label} ({bucket.length})
                          </h4>
                        </div>
                        <div className="space-y-3 pl-5">
                          {bucket.map((cluster, idx) => renderRow(cluster, idx, delay + 0.1))}
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
              )}
            </SpotlightCard>
          </motion.div>
        );
      })()}

      {/* â”€â”€ Ticket Export Modal â”€â”€ */}
      {exportCluster && (
        <TicketExportModal
          cluster={{
            ...exportCluster,
            ...(clusterDetails.get(exportCluster.id) ?? {}),
          }}
          appName={analytics.upload_data?.filename?.replace(/\.csv$/i, '') ?? undefined}
          onClose={() => setExportCluster(null)}
        />
      )}

      {/* ── Report export error toast ── */}
      <AnimatePresence>
        {reportExportError && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/30 backdrop-blur-xl shadow-lg max-w-md"
          >
            <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
            <span className="text-sm text-red-200">{reportExportError}</span>
            <button
              onClick={() => setReportExportError(null)}
              className="ml-1 text-red-300/70 hover:text-red-200 transition-colors"
            >
              ✕
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
