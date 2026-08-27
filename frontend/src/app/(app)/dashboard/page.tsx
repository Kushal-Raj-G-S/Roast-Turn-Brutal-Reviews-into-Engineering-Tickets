"use client";

/**
 * Dashboard Page - Authenticated with Supabase
 * =============================================
 * Features: Real user data, roast history, live stats
 */

import { motion, AnimatePresence } from "framer-motion";
import { Flame, TrendingUp, Clock, CheckCircle2, Database, AlertTriangle, Undo2, X, Trophy, LayoutGrid } from "lucide-react";
import { KanbanBoard, RoastArena, Ticket } from "@/components/ui";
import { SpotlightCard } from "@/components/ui";
import { UsageDashboard } from "@/components/dashboard/UsageDashboard";
import { useEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api-client";

const STATUS_LABELS: Record<Ticket["status"], string> = {
  fresh: "Fresh Roast",
  assigned: "Assigned",
  fixing: "Fixing",
  resolved: "Resolved",
  wont_fix: "Won't Fix",
};

interface MoveToast {
  kind: "success" | "error";
  message: string;
  /** Only set on success -- lets the user immediately reverse a drag they didn't mean to make. */
  undo?: () => void;
}

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
  const [view, setView] = useState<"arena" | "board">("arena");
  const [moveToast, setMoveToast] = useState<MoveToast | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showMoveToast = (toast: MoveToast) => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setMoveToast(toast);
    toastTimerRef.current = setTimeout(() => setMoveToast(null), 5000);
  };

  // Drag-and-drop status changes -- KanbanBoard's 5 visual columns now map
  // 1:1 onto the backend's 5 real statuses (see PATCH /clusters/{id}/status).
  // Optimistic update first (the board should feel instant), then the real
  // PATCH; revert on failure so the board never silently disagrees with
  // the database.
  const VISUAL_TO_BACKEND_STATUS: Record<Ticket["status"], "fresh_roast" | "assigned" | "in_progress" | "resolved" | "wont_fix"> = {
    fresh: "fresh_roast",
    assigned: "assigned",
    fixing: "in_progress",
    resolved: "resolved",
    wont_fix: "wont_fix",
  };

  // Same fused score the backend's /triage-queue endpoint computes
  // (severity + AI faithfulness + regression signal + log-scaled volume) --
  // mirrored here so cards within a column are already ranked "fix this
  // first" without an extra round-trip. Kept in sync with
  // backend/app/api/bulk_routes.py's _priority_score. Returns the four
  // components separately too -- Roast Arena renders them as a literal
  // power bar instead of a hidden sort key.
  const SEVERITY_WEIGHT: Record<string, number> = { critical: 100, high: 70, medium: 40, low: 15 };
  const priorityBreakdown = (cluster: any) => {
    const severityWeight = SEVERITY_WEIGHT[(cluster.severity || "").toLowerCase()] ?? 20;
    const faithfulnessRaw =
      typeof cluster.ai_metadata?.eval_scores?.faithfulness === "number"
        ? cluster.ai_metadata.eval_scores.faithfulness
        : 0.5;
    const regressionBoost = cluster.regression_detected
      ? 30 * (typeof cluster.regression_confidence === "number" ? cluster.regression_confidence : 0.5)
      : 0;
    const velocity = Math.log1p(Math.max(cluster.review_count || 0, 0)) * 5;
    return { severityWeight, faithfulness: faithfulnessRaw * 20, regressionBoost, velocity };
  };
  const priorityScore = (cluster: any): number => {
    const b = priorityBreakdown(cluster);
    return b.severityWeight + b.faithfulness + b.regressionBoost + b.velocity;
  };

  const handleStatusChange = async (ticketId: string, newVisualStatus: Ticket["status"], isUndo = false) => {
    const ticket = tickets.find((t) => t.id === ticketId);
    if (!ticket || ticket.status === newVisualStatus) return;

    const previousStatus = ticket.status;
    setMovingTicketId(ticketId);
    setTickets((prev) => prev.map((t) => (t.id === ticketId ? { ...t, status: newVisualStatus } : t)));

    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (session?.access_token) apiClient.setToken(session.access_token);
      await apiClient.updateClusterStatus(Number(ticketId), VISUAL_TO_BACKEND_STATUS[newVisualStatus]);

      // Confirms the drop actually did something -- without this, a
      // successful move looks identical to a dropped/ignored click. Skip
      // the "you can undo this" affordance on the undo action itself, or
      // undoing an undo would just chain forever.
      showMoveToast({
        kind: "success",
        message: `Moved "${ticket.title.slice(0, 40)}${ticket.title.length > 40 ? "…" : ""}" to ${STATUS_LABELS[newVisualStatus]}`,
        undo: isUndo ? undefined : () => handleStatusChange(ticketId, previousStatus, true),
      });
    } catch (err) {
      console.error("Failed to update cluster status:", err);
      // Revert -- the drag looked like it worked but the database rejected it.
      setTickets((prev) => prev.map((t) => (t.id === ticketId ? { ...t, status: previousStatus } : t)));
      showMoveToast({ kind: "error", message: "Couldn't move that ticket — it's back where it was." });
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

      // Convert clusters to tickets for Kanban board, ranked by the same
      // fused priority score as the backend triage queue -- so within each
      // column, the card most worth fixing first is already on top.
      const clusterTickets: Ticket[] = [...allClusters]
        .sort((a, b) => priorityScore(b) - priorityScore(a))
        .slice(0, 50)
        .map((cluster: any) => ({
          id: String(cluster.id),
          title: cluster.title,
          summary: cluster.rca_hypothesis || 'No description available',
          severity: cluster.severity,
          cluster_id: cluster.id,
          app_version: "N/A",
          device_type: "All",
          review_count: cluster.review_count || 0,
          status: cluster.status === 'fresh_roast' ? 'fresh' :
                  cluster.status === 'assigned' ? 'assigned' :
                  cluster.status === 'in_progress' ? 'fixing' :
                  cluster.status === 'resolved' ? 'resolved' :
                  cluster.status === 'wont_fix' ? 'wont_fix' : 'fresh',
          priorityScore: priorityScore(cluster),
          priorityBreakdown: priorityBreakdown(cluster),
          regressionDetected: !!cluster.regression_detected,
          regressionOfTitle: cluster.regression_of_title ?? null,
          regressionConfidence: cluster.regression_confidence ?? null,
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
            <div className="flex items-center gap-2">
              <div className="flex items-center rounded-full bg-white/5 border border-white/10 p-0.5">
                <button
                  onClick={() => setView("arena")}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold transition-colors ${
                    view === "arena" ? "bg-white/10 text-white" : "text-neutral-500 hover:text-neutral-300"
                  }`}
                >
                  <Trophy className="w-3.5 h-3.5" />
                  Arena
                </button>
                <button
                  onClick={() => setView("board")}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold transition-colors ${
                    view === "board" ? "bg-white/10 text-white" : "text-neutral-500 hover:text-neutral-300"
                  }`}
                >
                  <LayoutGrid className="w-3.5 h-3.5" />
                  Board
                </button>
              </div>
              <button
                onClick={() => router.push('/clusters')}
                className="px-4 py-2 rounded-lg bg-gradient-to-r from-orange-500 to-red-600 text-white font-medium hover:from-orange-600 hover:to-red-700 transition-all"
              >
                View All Datasets
              </button>
            </div>
          )}
        </div>
        {view === "arena" ? (
          <RoastArena tickets={tickets} onStatusChange={handleStatusChange} movingId={movingTicketId} />
        ) : (
          <KanbanBoard tickets={tickets} onStatusChange={handleStatusChange} movingId={movingTicketId} />
        )}
      </motion.div>

      {/* Drag-drop confirmation toast -- without this, a successful drop
          and an ignored/failed drop look identical to the user. */}
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 pointer-events-none">
        <AnimatePresence>
          {moveToast && (
            <motion.div
              initial={{ opacity: 0, y: 20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.95 }}
              className={`pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-xl border shadow-2xl backdrop-blur-xl ${
                moveToast.kind === "success"
                  ? "bg-emerald-950/90 border-emerald-500/30 text-emerald-100"
                  : "bg-red-950/90 border-red-500/30 text-red-100"
              }`}
            >
              {moveToast.kind === "success" ? (
                <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
              ) : (
                <AlertTriangle className="w-4 h-4 shrink-0 text-red-400" />
              )}
              <span className="text-sm">{moveToast.message}</span>
              {moveToast.undo && (
                <button
                  onClick={() => {
                    moveToast.undo?.();
                    setMoveToast(null);
                  }}
                  className="flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-md bg-white/10 hover:bg-white/20 transition-colors shrink-0"
                >
                  <Undo2 className="w-3 h-3" />
                  Undo
                </button>
              )}
              <button
                onClick={() => setMoveToast(null)}
                className="shrink-0 opacity-60 hover:opacity-100 transition-opacity"
                aria-label="Dismiss"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
