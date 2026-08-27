"use client";

/**
 * Dashboard Page - Authenticated with Supabase
 * =============================================
 * Features: Real user data, roast history, live stats
 */

import { motion } from "framer-motion";
import { Flame, TrendingUp, Clock, CheckCircle2, Database, AlertTriangle } from "lucide-react";
import { KanbanBoard, Ticket } from "@/components/ui";
import { SpotlightCard } from "@/components/ui";
import { UsageDashboard } from "@/components/dashboard/UsageDashboard";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api-client";

interface UserProfile {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  provider: string | null;
}

interface DashboardStats {
  total_reviews_analyzed: number;
  total_uploads: number;
  total_clusters: number;
  critical_issues: number;
  high_issues: number;
  medium_issues: number;
  low_issues: number;
  resolved_issues: number;
}

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [movingTicketId, setMovingTicketId] = useState<string | null>(null);

  // Drag-and-drop status changes -- KanbanBoard only knows the 3 visual
  // columns ("fresh"/"fixing"/"resolved"); the backend has 5 real statuses
  // (see PATCH /clusters/{id}/status), so this maps back the same way the
  // reverse mapping above narrows 5 down to 3. Optimistic update first (the
  // board should feel instant), then the real PATCH; revert on failure so
  // the board never silently disagrees with the database.
  const VISUAL_TO_BACKEND_STATUS: Record<Ticket["status"], "fresh_roast" | "in_progress" | "resolved"> = {
    fresh: "fresh_roast",
    fixing: "in_progress",
    resolved: "resolved",
  };

  const handleStatusChange = async (ticketId: string, newVisualStatus: Ticket["status"]) => {
    const ticket = tickets.find((t) => t.id === ticketId);
    if (!ticket || ticket.status === newVisualStatus) return;

    const previousStatus = ticket.status;
    setMovingTicketId(ticketId);
    setTickets((prev) => prev.map((t) => (t.id === ticketId ? { ...t, status: newVisualStatus } : t)));

    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (session?.access_token) apiClient.setToken(session.access_token);
      await apiClient.updateClusterStatus(Number(ticketId), VISUAL_TO_BACKEND_STATUS[newVisualStatus]);
    } catch (err) {
      console.error("Failed to update cluster status:", err);
      // Revert -- the drag looked like it worked but the database rejected it.
      setTickets((prev) => prev.map((t) => (t.id === ticketId ? { ...t, status: previousStatus } : t)));
    } finally {
      setMovingTicketId(null);
    }
  };

  useEffect(() => {
    checkUser();
  }, []);

  const checkUser = async () => {
    try {
      // Get current user
      const { data: { user: authUser } } = await supabase.auth.getUser();
      
      if (!authUser) {
        router.push('/login');
        return;
      }

      // Set user profile
      setUser({
        id: authUser.id,
        email: authUser.email!,
        full_name: authUser.user_metadata?.full_name || null,
        avatar_url: authUser.user_metadata?.avatar_url || null,
        provider: authUser.app_metadata?.provider || null,
      });

      // Fetch user's uploads
      const { data: uploads, error: uploadsError } = await supabase
        .from('uploads')
        .select('*')
        .eq('user_id', authUser.id)
        .eq('status', 'completed');

      if (uploadsError) {
        console.error('Error fetching uploads:', uploadsError);
      }

      const totalReviews = uploads?.reduce((sum, u) => sum + (u.total_reviews || 0), 0) || 0;
      const totalUploads = uploads?.length || 0;

      // Fetch clusters for user's uploads
      let allClusters: any[] = [];
      if (uploads && uploads.length > 0) {
        const uploadIds = uploads.map(u => u.id);
        
        const { data: clustersData, error: clustersError } = await supabase
          .from('clusters')
          .select('*')
          .in('upload_id', uploadIds)
          .order('created_at', { ascending: false });

        if (clustersError) {
          console.error('Error fetching clusters:', clustersError);
        } else {
          allClusters = clustersData || [];
        }
      }

      // Calculate stats from clusters
      const criticalCount = allClusters.filter(c => c.severity === 'critical').length;
      const highCount = allClusters.filter(c => c.severity === 'high').length;
      const mediumCount = allClusters.filter(c => c.severity === 'medium').length;
      const lowCount = allClusters.filter(c => c.severity === 'low').length;
      const resolvedCount = allClusters.filter(c => c.status === 'resolved').length;

      setStats({
        total_reviews_analyzed: totalReviews,
        total_uploads: totalUploads,
        total_clusters: allClusters.length,
        critical_issues: criticalCount,
        high_issues: highCount,
        medium_issues: mediumCount,
        low_issues: lowCount,
        resolved_issues: resolvedCount,
      });

      // Convert clusters to tickets for Kanban board
      const clusterTickets: Ticket[] = allClusters.slice(0, 50).map((cluster: any) => ({
        id: String(cluster.id),
        title: cluster.title,
        summary: cluster.rca_hypothesis || 'No description available',
        severity: cluster.severity,
        cluster_id: cluster.id,
        app_version: "N/A",
        device_type: "All",
        review_count: cluster.review_count || 0,
        status: cluster.status === 'fresh_roast' ? 'fresh' : 
                cluster.status === 'in_progress' ? 'fixing' : 
                cluster.status === 'resolved' ? 'resolved' : 'fresh',
      }));
      
      setTickets(clusterTickets);
      setLoading(false);
    } catch (error) {
      console.error('Error:', error);
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-orange-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-neutral-400">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  const dashboardStats = [
    {
      title: "Reviews Analyzed",
      value: stats?.total_reviews_analyzed?.toLocaleString() || "0",
      change: `${stats?.total_uploads || 0} upload${stats?.total_uploads !== 1 ? 's' : ''}`,
      icon: Database,
      color: "from-red-500 to-orange-600",
    },
    {
      title: "Issues Found",
      value: stats?.total_clusters?.toString() || "0",
      change: `${stats?.critical_issues || 0} critical`,
      icon: AlertTriangle,
      color: "from-orange-500 to-amber-500",
    },
    {
      title: "Issues Resolved",
      value: stats?.resolved_issues?.toString() || "0",
      change: `${stats?.total_clusters && stats?.total_clusters > 0 ? Math.round((stats.resolved_issues / stats.total_clusters) * 100) : 0}% complete`,
      icon: CheckCircle2,
      color: "from-emerald-500 to-green-600",
    },
    {
      title: "Severity Breakdown",
      value: `${stats?.high_issues || 0}H ${stats?.medium_issues || 0}M ${stats?.low_issues || 0}L`,
      change: "Distribution",
      icon: TrendingUp,
      color: "from-blue-500 to-cyan-500",
    },
  ];

  return (
    <div className="min-h-screen p-8 space-y-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">
            Dashboard
          </h1>
          <p className="text-neutral-400">
            Welcome back, {user?.full_name || user?.email || 'User'}! 🔥
          </p>
        </div>
      </motion.div>

      {/* Stats Grid */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4"
      >
        {dashboardStats.map((stat, i) => (
          <SpotlightCard key={i} className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-neutral-500 mb-1">{stat.title}</p>
                <p className="text-3xl font-bold text-white">{stat.value}</p>
                <p className="text-xs text-neutral-400 mt-1">{stat.change}</p>
              </div>
              <div
                className={`w-12 h-12 rounded-xl bg-gradient-to-br ${stat.color} flex items-center justify-center shadow-lg`}
              >
                <stat.icon className="w-6 h-6 text-white" />
              </div>
            </div>
          </SpotlightCard>
        ))}
      </motion.div>

      {/* Usage Dashboard */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
      >
        <UsageDashboard />
      </motion.div>

      {/* Kanban Board with Real Data */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
      >
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Flame className="w-5 h-5 text-orange-500" />
              Your Roast History
            </h2>
            <p className="text-neutral-500 text-sm mt-1">
              {tickets.length > 0 ? (
                <>
                  {tickets.length} issue{tickets.length !== 1 ? 's' : ''} found • 
                  <span className="text-red-500 ml-1">{stats?.critical_issues || 0} critical</span>
                  <span className="text-orange-500 ml-1">• {stats?.high_issues || 0} high</span>
                  <span className="text-yellow-500 ml-1">• {stats?.medium_issues || 0} medium</span>
                  <span className="text-blue-500 ml-1">• {stats?.low_issues || 0} low</span>
                </>
              ) : (
                'No reviews yet. Upload a CSV to start roasting! 🔥'
              )}
            </p>
          </div>
          {tickets.length > 0 && (
            <button
              onClick={() => router.push('/clusters')}
              className="px-4 py-2 rounded-lg bg-gradient-to-r from-orange-500 to-red-600 text-white font-medium hover:from-orange-600 hover:to-red-700 transition-all"
            >
              View All Datasets
            </button>
          )}
        </div>
        <KanbanBoard tickets={tickets} onStatusChange={handleStatusChange} movingId={movingTicketId} />
      </motion.div>
    </div>
  );
}
