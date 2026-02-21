"use client";

/**
 * Dashboard Page - Authenticated with Supabase
 * =============================================
 * Features: Real user data, roast history, live stats
 */

import { motion } from "framer-motion";
import { Flame, TrendingUp, Clock, CheckCircle2, LogOut, User } from "lucide-react";
import { KanbanBoard, Ticket } from "@/components/ui";
import { SpotlightCard } from "@/components/ui";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";
import { apiClient, Upload as UploadType, Cluster } from "@/lib/api-client";

interface UserProfile {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  provider: string | null;
}

interface UserStats {
  total_reviews_analyzed: number;
  total_issues_found: number;
  total_issues_resolved: number;
  average_sentiment_score: number | null;
}

// Mock ticket data - replace with API integration
const mockTickets: Ticket[] = [
  {
    id: "1",
    title: "App crashes on startup after update",
    summary: "Multiple users reporting crashes immediately after updating to v2.3.0. Stack traces point to authentication module initialization.",
    severity: "critical",
    cluster_id: "cluster-1",
    app_version: "2.3.0",
    device_type: "Android",
    review_count: 47,
    status: "fresh",
  },
  {
    id: "2",
    title: "Login takes too long",
    summary: "Users experiencing 10+ second delays during login. Likely related to slow token refresh endpoint.",
    severity: "high",
    cluster_id: "cluster-2",
    app_version: "2.2.8",
    device_type: "iOS",
    review_count: 23,
    status: "fresh",
  },
  {
    id: "3",
    title: "Dark mode colors are hard to read",
    summary: "Text contrast issues in dark mode, particularly in settings and profile screens.",
    severity: "medium",
    cluster_id: "cluster-3",
    app_version: "2.3.0",
    device_type: "All",
    review_count: 15,
    status: "fixing",
  },
  {
    id: "4",
    title: "Push notifications not working",
    summary: "Android users not receiving push notifications. May be related to new Firebase SDK version.",
    severity: "high",
    cluster_id: "cluster-4",
    app_version: "2.3.0",
    device_type: "Android",
    review_count: 31,
    status: "fixing",
  },
  {
    id: "5",
    title: "Battery drain issues",
    summary: "App consuming excessive battery in background. Users report 20-30% drain overnight.",
    severity: "medium",
    cluster_id: "cluster-5",
    app_version: "2.2.5",
    device_type: "iOS",
    review_count: 18,
    status: "resolved",
  },
  {
    id: "6",
    title: "Typo in onboarding screen",
    summary: "Welcome message contains spelling error on third onboarding slide.",
    severity: "low",
    cluster_id: "cluster-6",
    app_version: "2.3.0",
    device_type: "All",
    review_count: 5,
    status: "resolved",
  },
];

const stats = [
  {
    title: "Fresh Tickets",
    value: "12",
    change: "+3 today",
    icon: Flame,
    color: "from-red-500 to-orange-600",
  },
  {
    title: "In Progress",
    value: "5",
    change: "2 critical",
    icon: Clock,
    color: "from-orange-500 to-amber-500",
  },
  {
    title: "Resolved",
    value: "28",
    change: "+7 this week",
    icon: CheckCircle2,
    color: "from-emerald-500 to-green-600",
  },
  {
    title: "Response Time",
    value: "4.2h",
    change: "-23% avg",
    icon: TrendingUp,
    color: "from-blue-500 to-cyan-500",
  },
];

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [stats, setStats] = useState<UserStats | null>(null);
  const [uploads, setUploads] = useState<UploadType[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>(mockTickets); // Start with mock, replace with real data
  const [loading, setLoading] = useState(true);

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

      // Fetch user profile
      const { data: profile, error: profileError } = await supabase
        .from('profiles')
        .select('*')
        .eq('id', authUser.id)
        .single();

      if (profileError && profileError.code !== 'PGRST116') {
        console.error('Error fetching profile:', profileError);
      }

      setUser(profile || {
        id: authUser.id,
        email: authUser.email!,
        full_name: authUser.user_metadata?.full_name || null,
        avatar_url: authUser.user_metadata?.avatar_url || null,
        provider: authUser.app_metadata?.provider || null,
      });

      // Fetch user statistics
      const { data: userStats, error: statsError } = await supabase
        .from('user_statistics')
        .select('*')
        .eq('user_id', authUser.id)
        .single();

      if (statsError && statsError.code !== 'PGRST116') {
        console.error('Error fetching stats:', statsError);
      }

      setStats(userStats || {
        total_reviews_analyzed: 0,
        total_issues_found: 0,
        total_issues_resolved: 0,
        average_sentiment_score: null,
      });

      // Fetch uploads from backend API
      const { data: { session } } = await supabase.auth.getSession();
      if (session) {
        apiClient.setToken(session.access_token);
        
        try {
          const uploadsData = await apiClient.getUploads();
          setUploads(uploadsData);
          
          // Convert uploads to tickets for display
          if (uploadsData.length > 0) {
            const allClusters: Ticket[] = [];
            
            for (const upload of uploadsData.slice(0, 3)) { // Get clusters from first 3 uploads
              try {
                const clusters = await apiClient.getUploadClusters(upload.id);
                
                clusters.forEach((cluster: Cluster, index: number) => {
                  allClusters.push({
                    id: cluster.id.toString(),
                    title: cluster.title,
                    summary: `From upload: ${upload.filename}`,
                    severity: cluster.severity as any,
                    cluster_id: cluster.cluster_uuid,
                    app_version: "N/A",
                    device_type: "All",
                    review_count: cluster.review_count || 0,
                    status: cluster.status === 'fresh_roast' ? 'fresh' : 
                            cluster.status === 'in_progress' ? 'fixing' : 
                            cluster.status === 'resolved' ? 'resolved' : 'fresh',
                  });
                });
              } catch (err) {
                console.error(`Error fetching clusters for upload ${upload.id}:`, err);
              }
            }
            
            if (allClusters.length > 0) {
              setTickets(allClusters);
            }
          }
        } catch (error) {
          console.error('Error fetching uploads:', error);
        }
      }

      // Fetch roast results
      const { data: results, error: resultsError } = await supabase
        .from('roast_results')
        .select('*')
        .eq('user_id', authUser.id)
        .order('created_at', { ascending: false })
        .limit(10);

      if (resultsError) {
        console.error('Error fetching roast results:', resultsError);
      }

      setLoading(false);
    } catch (error) {
      console.error('Error:', error);
      setLoading(false);
    }
  };

  const handleSignOut = async () => {
    await fetch('/api/auth/signout', { method: 'POST' });
    router.push('/');
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
      value: stats?.total_reviews_analyzed?.toString() || "0",
      change: "All time",
      icon: Flame,
      color: "from-red-500 to-orange-600",
    },
    {
      title: "Issues Found",
      value: stats?.total_issues_found?.toString() || "0",
      change: "Total detected",
      icon: Clock,
      color: "from-orange-500 to-amber-500",
    },
    {
      title: "Issues Resolved",
      value: stats?.total_issues_resolved?.toString() || "0",
      change: `${stats?.total_issues_found ? Math.round((stats.total_issues_resolved / stats.total_issues_found) * 100) : 0}% success`,
      icon: CheckCircle2,
      color: "from-emerald-500 to-green-600",
    },
    {
      title: "Avg Sentiment",
      value: stats?.average_sentiment_score?.toFixed(2) || "N/A",
      change: "Overall score",
      icon: TrendingUp,
      color: "from-blue-500 to-cyan-500",
    },
  ];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-2xl font-bold text-white">
          Welcome back, {user?.full_name || user?.email?.split('@')[0] || 'User'}! 👋
        </h1>
        <p className="text-neutral-500">Track and manage your roasted reviews</p>
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

      {/* Kanban Board with Real Data */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
      >
        <div className="mb-4">
          <h2 className="text-xl font-bold text-white">Your Roast History</h2>
          <p className="text-neutral-500 text-sm">
            {tickets.length > 0 ? `${tickets.length} review${tickets.length !== 1 ? 's' : ''} analyzed` : 'No reviews yet. Start roasting some bad reviews!'}
          </p>
        </div>
        <KanbanBoard tickets={tickets.length > 0 ? tickets : mockTickets} />
      </motion.div>
    </div>
  );
}
