"use client";

/**
 * Analytics Page - Review Analytics Dashboard
 * ============================================
 * Real-time insights and metrics from processed reviews
 */

import { motion } from "framer-motion";
import { 
  BarChart3, 
  TrendingUp, 
  PieChart, 
  Activity,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Target,
  Flame
} from "lucide-react";
import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { supabase } from "@/lib/supabase/client";
import { SpotlightCard } from "@/components/ui";

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
};

export default function AnalyticsPage() {
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAnalytics();
  }, []);

  const fetchAnalytics = async () => {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) return;

      apiClient.setToken(session.access_token);
      const data = await apiClient.getAnalytics();
      setAnalytics(data);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching analytics:', error);
      setLoading(false);
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
      {/* Page Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-2xl font-bold text-white">Analytics Dashboard</h1>
        <p className="text-neutral-500">Insights and trends from your reviews</p>
      </motion.div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <SpotlightCard className="p-6">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-neutral-500 mb-1">Reviews Analyzed</p>
                <p className="text-3xl font-bold text-white">
                  {user_statistics.total_reviews_analyzed.toLocaleString()}
                </p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500/20 to-cyan-500/20 border border-blue-500/20 flex items-center justify-center">
                <BarChart3 className="w-6 h-6 text-blue-400" />
              </div>
            </div>
          </SpotlightCard>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
        >
          <SpotlightCard className="p-6">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-neutral-500 mb-1">Issues Found</p>
                <p className="text-3xl font-bold text-white">
                  {user_statistics.total_issues_found}
                </p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-orange-500/20 to-red-500/20 border border-orange-500/20 flex items-center justify-center">
                <AlertTriangle className="w-6 h-6 text-orange-400" />
              </div>
            </div>
          </SpotlightCard>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <SpotlightCard className="p-6">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-neutral-500 mb-1">Resolved</p>
                <p className="text-3xl font-bold text-white">
                  {user_statistics.total_issues_resolved}
                </p>
                <p className="text-xs text-emerald-400 mt-1">
                  {resolutionRate}% resolution rate
                </p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-emerald-500/20 to-green-500/20 border border-emerald-500/20 flex items-center justify-center">
                <CheckCircle2 className="w-6 h-6 text-emerald-400" />
              </div>
            </div>
          </SpotlightCard>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
        >
          <SpotlightCard className="p-6">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-neutral-500 mb-1">Avg Sentiment</p>
                <p className="text-3xl font-bold text-white">
                  {user_statistics.average_sentiment_score.toFixed(2)}
                </p>
                <p className="text-xs text-neutral-400 mt-1">
                  -1 (negative) to +1 (positive)
                </p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 border border-purple-500/20 flex items-center justify-center">
                <Activity className="w-6 h-6 text-purple-400" />
              </div>
            </div>
          </SpotlightCard>
        </motion.div>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Severity Distribution */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <SpotlightCard className="p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-red-500/20 to-orange-500/20 border border-red-500/20 flex items-center justify-center">
                <Flame className="w-5 h-5 text-red-400" />
              </div>
              <div>
                <h3 className="font-bold text-white">Issue Severity</h3>
                <p className="text-sm text-neutral-500">Distribution by impact level</p>
              </div>
            </div>

            {totalSeverity > 0 ? (
              <div className="space-y-4">
                {/* Critical */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-neutral-300">Critical</span>
                    <span className="text-sm font-bold text-red-400">
                      {severity_distribution.critical} ({Math.round((severity_distribution.critical / totalSeverity) * 100)}%)
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-white/5 overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-red-500 to-red-600 rounded-full"
                      style={{ width: `${(severity_distribution.critical / totalSeverity) * 100}%` }}
                    />
                  </div>
                </div>

                {/* High */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-neutral-300">High</span>
                    <span className="text-sm font-bold text-orange-400">
                      {severity_distribution.high} ({Math.round((severity_distribution.high / totalSeverity) * 100)}%)
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-white/5 overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-orange-500 to-orange-600 rounded-full"
                      style={{ width: `${(severity_distribution.high / totalSeverity) * 100}%` }}
                    />
                  </div>
                </div>

                {/* Medium */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-neutral-300">Medium</span>
                    <span className="text-sm font-bold text-yellow-400">
                      {severity_distribution.medium} ({Math.round((severity_distribution.medium / totalSeverity) * 100)}%)
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-white/5 overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-yellow-500 to-yellow-600 rounded-full"
                      style={{ width: `${(severity_distribution.medium / totalSeverity) * 100}%` }}
                    />
                  </div>
                </div>

                {/* Low */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-neutral-300">Low</span>
                    <span className="text-sm font-bold text-blue-400">
                      {severity_distribution.low} ({Math.round((severity_distribution.low / totalSeverity) * 100)}%)
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-white/5 overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-blue-500 to-blue-600 rounded-full"
                      style={{ width: `${(severity_distribution.low / totalSeverity) * 100}%` }}
                    />
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-neutral-500 text-center py-8">No severity data available</p>
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
    </div>
  );
}
