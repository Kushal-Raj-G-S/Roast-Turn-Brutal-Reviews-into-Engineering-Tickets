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
} from "lucide-react";
import { useEffect, useState, useMemo, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { apiClient } from "@/lib/api-client";
import { supabase } from "@/lib/supabase/client";
import { SpotlightCard } from "@/components/ui";
import { TicketExportModal } from "@/components/ui/TicketExportModal";
import type { ClusterDetail } from "@/lib/api-client";

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
  }>;
  upload_data?: {
    filename: string;
    processing_time_seconds?: number;
    total_reviews?: number;
    filtered_noise?: number;
  };
};

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

  useEffect(() => {
    fetchAnalytics();
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
                  </span>
                )
                : "Comprehensive insights and trends from all your reviews"
              }
            </p>
          </div>
          <div className="flex items-center gap-3">
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
                  <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-red-500/20 to-orange-500/20 border border-red-500/20 flex items-center justify-center">
                    <Flame className="w-4 h-4 text-red-400" />
                  </div>
                  <div>
                    <h3 className="font-bold text-white">#1 User Complaint</h3>
                    <p className="text-xs text-neutral-500">Loudest cluster by review volume Â· {totalReviews.toLocaleString()} total reviews</p>
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
          const isRegression = !!cluster.regression_detected;

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
                      {/* âš¡ Spike  /  â†© Regression badges */}
                      {(isSpiking || isRegression) && (
                        <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
                          {isSpiking && (
                            <span className="inline-flex items-center gap-1 text-[9px] font-black px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30 tracking-wide">
                              <Zap className="w-2.5 h-2.5" />SPIKING
                            </span>
                          )}
                          {isRegression && (
                            <span
                              className="inline-flex items-center gap-1 text-[9px] font-black px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-400 border border-purple-500/30 tracking-wide cursor-help"
                              title={cluster.regression_of_title
                                ? `Previously resolved: "${cluster.regression_of_title}"`
                                : 'This issue was previously resolved and has re-appeared'}
                            >
                              <RotateCcw className="w-2.5 h-2.5" />REGRESSION
                            </span>
                          )}
                        </div>
                      )}
                      <p className="text-sm text-white font-medium leading-snug">{cluster.title}</p>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className={`text-xs ${s.color} font-medium whitespace-nowrap`}>
                        {cluster.review_count} review{cluster.review_count !== 1 ? 's' : ''}
                      </span>
                      {isExpanded
                        ? <ChevronUp className={`w-4 h-4 ${s.color}`} />
                        : <ChevronDown className={`w-4 h-4 ${s.color}`} />}
                    </div>
                  </div>
                </motion.button>

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

              {/* Accordion â€” sample reviews */}
              <AnimatePresence>
                {isExpanded && details?.sample_reviews && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.25, ease: 'easeInOut' }}
                    className={`border-t ${s.border}`}
                  >
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
                  </div>
                </div>

                {/* Signal summary badges + export hint */}
                <div className="flex flex-wrap items-center gap-2">
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

              {/* Severity buckets */}
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
    </div>
  );
}
