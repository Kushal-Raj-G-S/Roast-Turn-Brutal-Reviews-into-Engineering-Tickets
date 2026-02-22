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
  Star
} from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiClient } from "@/lib/api-client";
import { supabase } from "@/lib/supabase/client";
import { SpotlightCard } from "@/components/ui";
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
  const uploadId = searchParams?.get('upload_id');
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedClusters, setExpandedClusters] = useState<Set<number>>(new Set());
  const [clusterDetails, setClusterDetails] = useState<Map<number, ClusterDetail>>(new Map());

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
        }
      } else {
        // Fetch overall analytics
        apiClient.setToken(session.access_token);
        const data = await apiClient.getAnalytics();
        
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
    <div className="space-y-6">
      {/* Page Header with Upload Info */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white mb-2">Analytics Dashboard</h1>
            <p className="text-neutral-400">
              {uploadId 
                ? `Showing results for Upload #${uploadId} • ${user_statistics.total_reviews_analyzed.toLocaleString()} reviews processed`
                : "Comprehensive insights and trends from all your reviews"
              }
            </p>
            {analytics.upload_data?.processing_time_seconds && (
              <p className="text-sm text-green-400 mt-1">
                ⚡ Processed in {analytics.upload_data.processing_time_seconds}s
                {analytics.upload_data.filtered_noise && (
                  <span className="text-neutral-500"> • Filtered {analytics.upload_data.filtered_noise} noise reviews</span>
                )}
              </p>
            )}
          </div>
          {uploadId && (
            <div className="px-4 py-2 rounded-xl bg-gradient-to-r from-orange-500/20 to-red-500/20 border border-orange-500/30">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-orange-500 animate-pulse"></div>
                <span className="text-sm font-medium text-orange-300">Latest Upload</span>
              </div>
            </div>
          )}
        </div>
      </motion.div>

      {/* Key Metrics - Enhanced */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <SpotlightCard className="p-6 relative overflow-hidden">
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
                  <div className="h-full w-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-500"></div>
                </div>
                <span className="text-xs text-blue-400 font-medium">100%</span>
              </div>
            </div>
          </SpotlightCard>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
        >
          <SpotlightCard className="p-6 relative overflow-hidden">
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
              <p className="text-4xl font-black text-white mb-1">
                {user_statistics.total_issues_found}
              </p>
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
          transition={{ delay: 0.2 }}
        >
          <SpotlightCard className="p-6 relative overflow-hidden">
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
              <p className="text-4xl font-black text-white mb-1">
                {analytics?.upload_data?.filtered_noise || 0}
              </p>
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
          transition={{ delay: 0.25 }}
        >
          <SpotlightCard className="p-6 relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-purple-500/10 to-transparent rounded-full blur-2xl"></div>
            <div className="relative">
              <div className="flex items-start justify-between mb-4">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 border border-purple-500/20 flex items-center justify-center">
                  <Activity className="w-6 h-6 text-purple-400" />
                </div>
                <div className="text-right">
                  <p className="text-xs text-neutral-500 uppercase tracking-wider">Avg</p>
                </div>
              </div>
              <p className="text-sm text-neutral-400 mb-2">Avg Sentiment</p>
              <p className="text-4xl font-black text-white mb-1">
                {(() => {
                  const score = user_statistics.average_sentiment_score;
                  if (score === 0) {
                    // Calculate from ratings if available
                    const total = user_statistics.rating_1_count + user_statistics.rating_2_count + 
                                  user_statistics.rating_3_count + user_statistics.rating_4_count + 
                                  user_statistics.rating_5_count;
                    if (total > 0) {
                      const weightedSum = (user_statistics.rating_1_count * -1) + 
                                         (user_statistics.rating_2_count * -0.5) + 
                                         (user_statistics.rating_3_count * 0) + 
                                         (user_statistics.rating_4_count * 0.5) + 
                                         (user_statistics.rating_5_count * 1);
                      return (weightedSum / total).toFixed(2);
                    }
                  }
                  return score.toFixed(2);
                })()}
              </p>
              <div className="flex items-center gap-2 mt-3">
                <span className="text-xs text-neutral-500">-1.0 (negative) to +1.0 (positive)</span>
              </div>
            </div>
          </SpotlightCard>
        </motion.div>
      </div>

      {/* Charts Row - Enhanced Severity Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Severity Distribution */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <SpotlightCard className="p-6 h-full">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-red-500/20 to-orange-500/20 border border-red-500/20 flex items-center justify-center">
                  <Flame className="w-5 h-5 text-red-400" />
                </div>
                <div>
                  <h3 className="font-bold text-white">Severity Distribution</h3>
                  <p className="text-sm text-neutral-500">{totalSeverity} total issues categorized</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-2xl font-black text-white">{totalSeverity}</p>
                <p className="text-xs text-neutral-500">Issues</p>
              </div>
            </div>

            {totalSeverity > 0 ? (() => {
              // Calculate max count for relative bar scaling (max severity gets 100% bar width)
              const maxCount = Math.max(
                severity_distribution.critical,
                severity_distribution.high,
                severity_distribution.medium,
                severity_distribution.low
              );
              
              return (
              <div className="space-y-4">
                {/* Critical */}
                <div className="group hover:bg-red-500/5 p-3 rounded-lg transition-colors">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-red-500 shadow-lg shadow-red-500/50"></div>
                      <span className="text-sm font-bold text-red-400 uppercase tracking-wider">Critical</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-lg font-black text-white">{severity_distribution.critical}</span>
                      <span className="text-sm font-bold text-red-400 min-w-[45px] text-right">
                        {Math.round((severity_distribution.critical / totalSeverity) * 100)}%
                      </span>
                    </div>
                  </div>
                  <div className="h-3 rounded-full bg-white/5 overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${(severity_distribution.critical / maxCount) * 100}%` }}
                      transition={{ duration: 0.8, delay: 0.3 }}
                      className="h-full bg-gradient-to-r from-red-600 via-red-500 to-red-400 rounded-full shadow-lg shadow-red-500/30"
                    />
                  </div>
                </div>

                {/* High */}
                <div className="group hover:bg-orange-500/5 p-3 rounded-lg transition-colors">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-orange-500 shadow-lg shadow-orange-500/50"></div>
                      <span className="text-sm font-bold text-orange-400 uppercase tracking-wider">High</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-lg font-black text-white">{severity_distribution.high}</span>
                      <span className="text-sm font-bold text-orange-400 min-w-[45px] text-right">
                        {Math.round((severity_distribution.high / totalSeverity) * 100)}%
                      </span>
                    </div>
                  </div>
                  <div className="h-3 rounded-full bg-white/5 overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${(severity_distribution.high / maxCount) * 100}%` }}
                      transition={{ duration: 0.8, delay: 0.4 }}
                      className="h-full bg-gradient-to-r from-orange-600 via-orange-500 to-orange-400 rounded-full shadow-lg shadow-orange-500/30"
                    />
                  </div>
                </div>

                {/* Medium */}
                <div className="group hover:bg-yellow-500/5 p-3 rounded-lg transition-colors">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-yellow-500 shadow-lg shadow-yellow-500/50"></div>
                      <span className="text-sm font-bold text-yellow-400 uppercase tracking-wider">Medium</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-lg font-black text-white">{severity_distribution.medium}</span>
                      <span className="text-sm font-bold text-yellow-400 min-w-[45px] text-right">
                        {Math.round((severity_distribution.medium / totalSeverity) * 100)}%
                      </span>
                    </div>
                  </div>
                  <div className="h-3 rounded-full bg-white/5 overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${(severity_distribution.medium / maxCount) * 100}%` }}
                      transition={{ duration: 0.8, delay: 0.5 }}
                      className="h-full bg-gradient-to-r from-yellow-600 via-yellow-500 to-yellow-400 rounded-full shadow-lg shadow-yellow-500/30"
                    />
                  </div>
                </div>

                {/* Low */}
                <div className="group hover:bg-blue-500/5 p-3 rounded-lg transition-colors">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-blue-500 shadow-lg shadow-blue-500/50"></div>
                      <span className="text-sm font-bold text-blue-400 uppercase tracking-wider">Low</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-lg font-black text-white">{severity_distribution.low}</span>
                      <span className="text-sm font-bold text-blue-400 min-w-[45px] text-right">
                        {Math.round((severity_distribution.low / totalSeverity) * 100)}%
                      </span>
                    </div>
                  </div>
                  <div className="h-3 rounded-full bg-white/5 overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${(severity_distribution.low / maxCount) * 100}%` }}
                      transition={{ duration: 0.8, delay: 0.6 }}
                      className="h-full bg-gradient-to-r from-blue-600 via-blue-500 to-blue-400 rounded-full shadow-lg shadow-blue-500/30"
                    />
                  </div>
                </div>
              </div>
              );
            })() : (
              <p className="text-neutral-500 text-center py-12">No severity data available</p>
            )}
          </SpotlightCard>
        </motion.div>

        {/* Status Distribution */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35 }}
        >
          <SpotlightCard className="p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-emerald-500/20 to-green-500/20 border border-emerald-500/20 flex items-center justify-center">
                <Target className="w-5 h-5 text-emerald-400" />
              </div>
              <div>
                <h3 className="font-bold text-white">Issue Status</h3>
                <p className="text-sm text-neutral-500">Current workflow state</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 rounded-xl bg-orange-500/10 border border-orange-500/20">
                <div className="flex items-center gap-2 mb-2">
                  <Flame className="w-4 h-4 text-orange-400" />
                  <span className="text-xs text-neutral-400">Fresh Roast</span>
                </div>
                <p className="text-2xl font-bold text-white">{status_distribution.fresh_roast}</p>
              </div>

              <div className="p-4 rounded-xl bg-blue-500/10 border border-blue-500/20">
                <div className="flex items-center gap-2 mb-2">
                  <Target className="w-4 h-4 text-blue-400" />
                  <span className="text-xs text-neutral-400">Assigned</span>
                </div>
                <p className="text-2xl font-bold text-white">{status_distribution.assigned}</p>
              </div>

              <div className="p-4 rounded-xl bg-yellow-500/10 border border-yellow-500/20">
                <div className="flex items-center gap-2 mb-2">
                  <Clock className="w-4 h-4 text-yellow-400" />
                  <span className="text-xs text-neutral-400">In Progress</span>
                </div>
                <p className="text-2xl font-bold text-white">{status_distribution.in_progress}</p>
              </div>

              <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span className="text-xs text-neutral-400">Resolved</span>
                </div>
                <p className="text-2xl font-bold text-white">{status_distribution.resolved}</p>
              </div>
            </div>
          </SpotlightCard>
        </motion.div>
      </div>

      {/* Rating Distribution & Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Rating Distribution */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
        >
          <SpotlightCard className="p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-amber-500/20 to-yellow-500/20 border border-amber-500/20 flex items-center justify-center">
                <PieChart className="w-5 h-5 text-amber-400" />
              </div>
              <div>
                <h3 className="font-bold text-white">Rating Distribution</h3>
                <p className="text-sm text-neutral-500">{totalRatings.toLocaleString()} total ratings</p>
              </div>
            </div>

            {totalRatings > 0 ? (
              <div className="space-y-3">
                {[5, 4, 3, 2, 1].map((rating) => {
                  const percentage = getRatingPercentage(rating);
                  const count = getRatingCount(rating);
                  
                  return (
                    <div key={rating}>
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-neutral-300">{rating} ⭐</span>
                        </div>
                        <span className="text-sm text-neutral-400">
                          {count} ({percentage.toFixed(1)}%)
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-white/5 overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-amber-500 to-yellow-500 rounded-full"
                          style={{ width: `${percentage}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-neutral-500 text-center py-8">No ratings data available</p>
            )}
          </SpotlightCard>
        </motion.div>

        {/* Recent Activity */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.45 }}
        >
          <SpotlightCard className="p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-cyan-500/20 to-blue-500/20 border border-cyan-500/20 flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-cyan-400" />
              </div>
              <div>
                <h3 className="font-bold text-white">Recent Activity</h3>
                <p className="text-sm text-neutral-500">Latest uploads and analysis</p>
              </div>
            </div>

            {recent_activity.length > 0 ? (
              <div className="space-y-3">
                {recent_activity.map((activity, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between p-3 rounded-lg bg-white/5 border border-white/10"
                  >
                    <div className="flex-1">
                      <p className="text-sm font-medium text-white truncate">
                        {activity.filename}
                      </p>
                      <p className="text-xs text-neutral-500">
                        {new Date(activity.date).toLocaleDateString()}
                      </p>
                    </div>
                    <div className="flex items-center gap-4 text-sm">
                      <div className="text-right">
                        <p className="text-neutral-400">{activity.reviews}</p>
                        <p className="text-xs text-neutral-600">reviews</p>
                      </div>
                      <div className="text-right">
                        <p className="text-orange-400 font-bold">{activity.clusters}</p>
                        <p className="text-xs text-neutral-600">clusters</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-neutral-500 text-center py-8">No recent activity</p>
            )}
          </SpotlightCard>
        </motion.div>
      </div>

      {/* Detailed Clusters Section */}
      {analytics.clusters && analytics.clusters.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
        >
          <SpotlightCard className="p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-purple-500/20 to-pink-500/20 border border-purple-500/20 flex items-center justify-center">
                <FileText className="w-5 h-5 text-purple-400" />
              </div>
              <div>
                <h3 className="font-bold text-white">Issue Clusters Breakdown</h3>
                <p className="text-sm text-neutral-500">
                  {analytics.clusters.length} clusters identified
                  {uploadId && " from this upload"}
                </p>
              </div>
            </div>

            <div className="space-y-4">
              {/* Critical Issues */}
              {analytics.clusters.filter(c => c.severity === 'critical').length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-3 h-3 rounded-full bg-red-500"></div>
                    <h4 className="text-sm font-bold text-red-400 uppercase tracking-wider">
                      Critical ({analytics.clusters.filter(c => c.severity === 'critical').length})
                    </h4>
                  </div>
                  <div className="space-y-2 pl-5">
                    {analytics.clusters
                      .filter(c => c.severity === 'critical')
                      .map((cluster) => {
                        const isExpanded = expandedClusters.has(cluster.id);
                        const details = clusterDetails.get(cluster.id);
                        
                        return (
                          <div key={cluster.id} className="rounded-lg bg-red-500/10 border border-red-500/20 overflow-hidden">
                            <button
                              onClick={() => toggleCluster(cluster.id)}
                              className="w-full p-3 hover:bg-red-500/5 transition-colors text-left"
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="flex-1">
                                  <p className="text-sm text-white font-medium">{cluster.title}</p>
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className="text-xs text-red-400 font-medium whitespace-nowrap">
                                    {cluster.review_count} review{cluster.review_count !== 1 ? 's' : ''}
                                  </span>
                                  {isExpanded ? (
                                    <ChevronUp className="w-4 h-4 text-red-400" />
                                  ) : (
                                    <ChevronDown className="w-4 h-4 text-red-400" />
                                  )}
                                </div>
                              </div>
                            </button>
                            
                            <AnimatePresence>
                              {isExpanded && details?.sample_reviews && (
                                <motion.div
                                  initial={{ height: 0, opacity: 0 }}
                                  animate={{ height: "auto", opacity: 1 }}
                                  exit={{ height: 0, opacity: 0 }}
                                  transition={{ duration: 0.3 }}
                                  className="border-t border-red-500/20"
                                >
                                  <div className="p-4 space-y-3 bg-black/20">
                                    <p className="text-xs text-red-400 font-semibold uppercase tracking-wider">
                                      Sample Reviews ({details.sample_reviews.length})
                                    </p>
                                    {details.sample_reviews.map((review, idx) => (
                                      <div key={idx} className="p-3 rounded-md bg-red-500/5 border border-red-500/10">
                                        <div className="flex items-start gap-2 mb-2">
                                          {review.rating && (
                                            <div className="flex items-center gap-1">
                                              {Array.from({ length: 5 }).map((_, i) => (
                                                <Star
                                                  key={i}
                                                  className={`w-3 h-3 ${
                                                    i < review.rating
                                                      ? 'fill-yellow-500 text-yellow-500'
                                                      : 'text-neutral-700'
                                                  }`}
                                                />
                                              ))}
                                            </div>
                                          )}
                                          {review.device && (
                                            <span className="text-xs text-neutral-500">• {review.device}</span>
                                          )}
                                          {review.version && (
                                            <span className="text-xs text-neutral-500">• v{review.version}</span>
                                          )}
                                        </div>
                                        <p className="text-sm text-neutral-300 leading-relaxed whitespace-pre-wrap">
                                          {review.content}
                                        </p>
                                      </div>
                                    ))}
                                  </div>
                                </motion.div>
                              )}
                            </AnimatePresence>
                          </div>
                        );
                      })}
                  </div>
                </div>
              )}

              {/* High Priority Issues */}
              {analytics.clusters.filter(c => c.severity === 'high').length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-3 h-3 rounded-full bg-orange-500"></div>
                    <h4 className="text-sm font-bold text-orange-400 uppercase tracking-wider">
                      High ({analytics.clusters.filter(c => c.severity === 'high').length})
                    </h4>
                  </div>
                  <div className="space-y-2 pl-5">
                    {analytics.clusters
                      .filter(c => c.severity === 'high')
                      .map((cluster) => {
                        const isExpanded = expandedClusters.has(cluster.id);
                        const details = clusterDetails.get(cluster.id);
                        
                        return (
                          <div key={cluster.id} className="rounded-lg bg-orange-500/10 border border-orange-500/20 overflow-hidden">
                            <button
                              onClick={() => toggleCluster(cluster.id)}
                              className="w-full p-3 hover:bg-orange-500/5 transition-colors text-left"
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="flex-1">
                                  <p className="text-sm text-white font-medium">{cluster.title}</p>
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className="text-xs text-orange-400 font-medium whitespace-nowrap">
                                    {cluster.review_count} review{cluster.review_count !== 1 ? 's' : ''}
                                  </span>
                                  {isExpanded ? (
                                    <ChevronUp className="w-4 h-4 text-orange-400" />
                                  ) : (
                                    <ChevronDown className="w-4 h-4 text-orange-400" />
                                  )}
                                </div>
                              </div>
                            </button>
                            
                            <AnimatePresence>
                              {isExpanded && details?.sample_reviews && (
                                <motion.div
                                  initial={{ height: 0, opacity: 0 }}
                                  animate={{ height: "auto", opacity: 1 }}
                                  exit={{ height: 0, opacity: 0 }}
                                  transition={{ duration: 0.3 }}
                                  className="border-t border-orange-500/20"
                                >
                                  <div className="p-4 space-y-3 bg-black/20">
                                    <p className="text-xs text-orange-400 font-semibold uppercase tracking-wider">
                                      Sample Reviews ({details.sample_reviews.length})
                                    </p>
                                    {details.sample_reviews.map((review, idx) => (
                                      <div key={idx} className="p-3 rounded-md bg-orange-500/5 border border-orange-500/10">
                                        <div className="flex items-start gap-2 mb-2">
                                          {review.rating && (
                                            <div className="flex items-center gap-1">
                                              {Array.from({ length: 5 }).map((_, i) => (
                                                <Star
                                                  key={i}
                                                  className={`w-3 h-3 ${
                                                    i < review.rating
                                                      ? 'fill-yellow-500 text-yellow-500'
                                                      : 'text-neutral-700'
                                                  }`}
                                                />
                                              ))}
                                            </div>
                                          )}
                                          {review.device && (
                                            <span className="text-xs text-neutral-500">• {review.device}</span>
                                          )}
                                          {review.version && (
                                            <span className="text-xs text-neutral-500">• v{review.version}</span>
                                          )}
                                        </div>
                                        <p className="text-sm text-neutral-300 leading-relaxed whitespace-pre-wrap">
                                          {review.content}
                                        </p>
                                      </div>
                                    ))}
                                  </div>
                                </motion.div>
                              )}
                            </AnimatePresence>
                          </div>
                        );
                      })}
                  </div>
                </div>
              )}

              {/* Medium Priority Issues */}
              {analytics.clusters.filter(c => c.severity === 'medium').length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
                    <h4 className="text-sm font-bold text-yellow-400 uppercase tracking-wider">
                      Medium ({analytics.clusters.filter(c => c.severity === 'medium').length})
                    </h4>
                  </div>
                  <div className="space-y-2 pl-5">
                    {analytics.clusters
                      .filter(c => c.severity === 'medium')
                      .map((cluster) => {
                        const isExpanded = expandedClusters.has(cluster.id);
                        const details = clusterDetails.get(cluster.id);
                        
                        return (
                          <div key={cluster.id} className="rounded-lg bg-yellow-500/10 border border-yellow-500/20 overflow-hidden">
                            <button
                              onClick={() => toggleCluster(cluster.id)}
                              className="w-full p-3 hover:bg-yellow-500/5 transition-colors text-left"
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="flex-1">
                                  <p className="text-sm text-white font-medium">{cluster.title}</p>
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className="text-xs text-yellow-400 font-medium whitespace-nowrap">
                                    {cluster.review_count} review{cluster.review_count !== 1 ? 's' : ''}
                                  </span>
                                  {isExpanded ? (
                                    <ChevronUp className="w-4 h-4 text-yellow-400" />
                                  ) : (
                                    <ChevronDown className="w-4 h-4 text-yellow-400" />
                                  )}
                                </div>
                              </div>
                            </button>
                            
                            <AnimatePresence>
                              {isExpanded && details?.sample_reviews && (
                                <motion.div
                                  initial={{ height: 0, opacity: 0 }}
                                  animate={{ height: "auto", opacity: 1 }}
                                  exit={{ height: 0, opacity: 0 }}
                                  transition={{ duration: 0.3 }}
                                  className="border-t border-yellow-500/20"
                                >
                                  <div className="p-4 space-y-3 bg-black/20">
                                    <p className="text-xs text-yellow-400 font-semibold uppercase tracking-wider">
                                      Sample Reviews ({details.sample_reviews.length})
                                    </p>
                                    {details.sample_reviews.map((review, idx) => (
                                      <div key={idx} className="p-3 rounded-md bg-yellow-500/5 border border-yellow-500/10">
                                        <div className="flex items-start gap-2 mb-2">
                                          {review.rating && (
                                            <div className="flex items-center gap-1">
                                              {Array.from({ length: 5 }).map((_, i) => (
                                                <Star
                                                  key={i}
                                                  className={`w-3 h-3 ${
                                                    i < review.rating
                                                      ? 'fill-yellow-500 text-yellow-500'
                                                      : 'text-neutral-700'
                                                  }`}
                                                />
                                              ))}
                                            </div>
                                          )}
                                          {review.device && (
                                            <span className="text-xs text-neutral-500">• {review.device}</span>
                                          )}
                                          {review.version && (
                                            <span className="text-xs text-neutral-500">• v{review.version}</span>
                                          )}
                                        </div>
                                        <p className="text-sm text-neutral-300 leading-relaxed whitespace-pre-wrap">
                                          {review.content}
                                        </p>
                                      </div>
                                    ))}
                                  </div>
                                </motion.div>
                              )}
                            </AnimatePresence>
                          </div>
                        );
                      })}
                  </div>
                </div>
              )}

              {/* Low Priority Issues */}
              {analytics.clusters.filter(c => c.severity === 'low').length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-3 h-3 rounded-full bg-blue-500"></div>
                    <h4 className="text-sm font-bold text-blue-400 uppercase tracking-wider">
                      Low ({analytics.clusters.filter(c => c.severity === 'low').length})
                    </h4>
                  </div>
                  <div className="space-y-2 pl-5">
                    {analytics.clusters
                      .filter(c => c.severity === 'low')
                      .map((cluster) => {
                        const isExpanded = expandedClusters.has(cluster.id);
                        const details = clusterDetails.get(cluster.id);
                        
                        return (
                          <div key={cluster.id} className="rounded-lg bg-blue-500/10 border border-blue-500/20 overflow-hidden">
                            <button
                              onClick={() => toggleCluster(cluster.id)}
                              className="w-full p-3 hover:bg-blue-500/5 transition-colors text-left"
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="flex-1">
                                  <p className="text-sm text-white font-medium">{cluster.title}</p>
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className="text-xs text-blue-400 font-medium whitespace-nowrap">
                                    {cluster.review_count} review{cluster.review_count !== 1 ? 's' : ''}
                                  </span>
                                  {isExpanded ? (
                                    <ChevronUp className="w-4 h-4 text-blue-400" />
                                  ) : (
                                    <ChevronDown className="w-4 h-4 text-blue-400" />
                                  )}
                                </div>
                              </div>
                            </button>
                            
                            <AnimatePresence>
                              {isExpanded && details?.sample_reviews && (
                                <motion.div
                                  initial={{ height: 0, opacity: 0 }}
                                  animate={{ height: "auto", opacity: 1 }}
                                  exit={{ height: 0, opacity: 0 }}
                                  transition={{ duration: 0.3 }}
                                  className="border-t border-blue-500/20"
                                >
                                  <div className="p-4 space-y-3 bg-black/20">
                                    <p className="text-xs text-blue-400 font-semibold uppercase tracking-wider">
                                      Sample Reviews ({details.sample_reviews.length})
                                    </p>
                                    {details.sample_reviews.map((review, idx) => (
                                      <div key={idx} className="p-3 rounded-md bg-blue-500/5 border border-blue-500/10">
                                        <div className="flex items-start gap-2 mb-2">
                                          {review.rating && (
                                            <div className="flex items-center gap-1">
                                              {Array.from({ length: 5 }).map((_, i) => (
                                                <Star
                                                  key={i}
                                                  className={`w-3 h-3 ${
                                                    i < review.rating
                                                      ? 'fill-yellow-500 text-yellow-500'
                                                      : 'text-neutral-700'
                                                  }`}
                                                />
                                              ))}
                                            </div>
                                          )}
                                          {review.device && (
                                            <span className="text-xs text-neutral-500">• {review.device}</span>
                                          )}
                                          {review.version && (
                                            <span className="text-xs text-neutral-500">• v{review.version}</span>
                                          )}
                                        </div>
                                        <p className="text-sm text-neutral-300 leading-relaxed whitespace-pre-wrap">
                                          {review.content}
                                        </p>
                                      </div>
                                    ))}
                                  </div>
                                </motion.div>
                              )}
                            </AnimatePresence>
                          </div>
                        );
                      })}
                  </div>
                </div>
              )}
            </div>
          </SpotlightCard>
        </motion.div>
      )}
    </div>
  );
}
