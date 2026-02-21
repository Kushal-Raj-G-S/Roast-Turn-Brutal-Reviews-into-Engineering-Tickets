"use client";

/**
 * Clusters Page - Dataset History
 * ================================
 * Shows history of all uploaded datasets with their clusters
 * Click on any dataset to view its analytics
 */

import { motion } from "framer-motion";
import { 
  FileText, 
  Calendar, 
  TrendingUp, 
  Clock, 
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Database,
  Flame
} from "lucide-react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase/client";
import { SpotlightCard } from "@/components/ui";

type UploadHistory = {
  id: number;
  filename: string;
  total_reviews: number;
  filtered_noise: number;
  clusters_created: number;
  processing_time_seconds?: number;
  status: string;
  created_at: string;
  clusters?: Array<{
    id: number;
    title: string;
    severity: string;
    review_count: number;
  }>;
};

export default function ClustersPage() {
  const router = useRouter();
  const [uploads, setUploads] = useState<UploadHistory[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchUploadHistory();
  }, []);

  const fetchUploadHistory = async () => {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) {
        setLoading(false);
        return;
      }

      const user_id = session.user.id;

      // Fetch all uploads for this user
      const { data: uploadsData, error } = await supabase
        .from('uploads')
        .select('*')
        .eq('user_id', user_id)
        .order('created_at', { ascending: false });

      if (error) throw error;

      if (uploadsData) {
        // Fetch clusters for each upload
        const uploadsWithClusters = await Promise.all(
          uploadsData.map(async (upload) => {
            const { data: clustersData } = await supabase
              .from('clusters')
              .select('id, title, severity, review_count')
              .eq('upload_id', upload.id)
              .order('severity', { ascending: true })
              .limit(10); // Show top 10 clusters per upload

            return {
              ...upload,
              clusters: clustersData || []
            };
          })
        );

        setUploads(uploadsWithClusters);
      }
      
      setLoading(false);
    } catch (error) {
      console.error('Error fetching upload history:', error);
      setLoading(false);
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'text-red-400 bg-red-500/10 border-red-500/20';
      case 'high': return 'text-orange-400 bg-orange-500/10 border-orange-500/20';
      case 'medium': return 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20';
      case 'low': return 'text-blue-400 bg-blue-500/10 border-blue-500/20';
      default: return 'text-neutral-400 bg-neutral-500/10 border-neutral-500/20';
    }
  };

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'critical': return <Flame className="w-3 h-3" />;
      case 'high': return <AlertTriangle className="w-3 h-3" />;
      default: return <CheckCircle2 className="w-3 h-3" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return (
          <span className="flex items-center gap-1 px-2 py-1 rounded-md bg-green-500/10 border border-green-500/20 text-green-400 text-xs">
            <CheckCircle2 className="w-3 h-3" />
            Completed
          </span>
        );
      case 'processing':
        return (
          <span className="flex items-center gap-1 px-2 py-1 rounded-md bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs">
            <Clock className="w-3 h-3 animate-spin" />
            Processing
          </span>
        );
      case 'failed':
        return (
          <span className="flex items-center gap-1 px-2 py-1 rounded-md bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
            <AlertTriangle className="w-3 h-3" />
            Failed
          </span>
        );
      default:
        return (
          <span className="flex items-center gap-1 px-2 py-1 rounded-md bg-neutral-500/10 border border-neutral-500/20 text-neutral-400 text-xs">
            <Clock className="w-3 h-3" />
            Pending
          </span>
        );
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <div className="animate-spin w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full mx-auto mb-4"></div>
          <p className="text-neutral-400">Loading dataset history...</p>
        </div>
      </div>
    );
  }

  if (uploads.length === 0) {
    return (
      <div className="text-center py-20">
        <Database className="w-16 h-16 text-neutral-600 mx-auto mb-4" />
        <h2 className="text-xl font-bold text-white mb-2">No Datasets Yet</h2>
        <p className="text-neutral-400 mb-6">
          Upload your first CSV file to start analyzing reviews
        </p>
        <button
          onClick={() => router.push('/upload')}
          className="px-6 py-3 rounded-xl bg-gradient-to-r from-orange-500 to-red-500 text-white font-medium hover:shadow-lg hover:shadow-orange-500/25 transition-all"
        >
          Upload Dataset
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white mb-2">Dataset History</h1>
            <p className="text-neutral-400">
              View all your uploaded datasets and their cluster analysis
            </p>
          </div>
          <div className="px-4 py-2 rounded-xl bg-gradient-to-r from-purple-500/20 to-pink-500/20 border border-purple-500/30">
            <p className="text-sm text-neutral-400">
              Total Datasets: <span className="text-white font-bold">{uploads.length}</span>
            </p>
          </div>
        </div>
      </motion.div>

      {/* Uploads Grid */}
      <div className="grid gap-6">
        {uploads.map((upload, index) => (
          <motion.div
            key={upload.id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
          >
            <SpotlightCard className="p-6">
              {/* Upload Header */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-start gap-3 flex-1">
                  <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-orange-500/20 to-red-500/20 border border-orange-500/30 flex items-center justify-center flex-shrink-0">
                    <FileText className="w-6 h-6 text-orange-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-lg font-bold text-white mb-1 truncate">{upload.filename}</h3>
                    <div className="flex items-center gap-3 text-sm text-neutral-500">
                      <span className="flex items-center gap-1">
                        <Calendar className="w-4 h-4" />
                        {new Date(upload.created_at).toLocaleDateString()}
                      </span>
                      {upload.processing_time_seconds && (
                        <span className="text-green-400">
                          ⚡ {upload.processing_time_seconds}s
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {getStatusBadge(upload.status)}
                </div>
              </div>

              {/* Stats Grid */}
              {upload.status === 'completed' && (
                <>
                  <div className="grid grid-cols-3 gap-4 mb-4">
                    <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                      <p className="text-xs text-neutral-500 mb-1">Total Reviews</p>
                      <p className="text-xl font-bold text-white">{upload.total_reviews?.toLocaleString() || 0}</p>
                    </div>
                    <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                      <p className="text-xs text-neutral-500 mb-1">Filtered</p>
                      <p className="text-xl font-bold text-orange-400">{upload.filtered_noise?.toLocaleString() || 0}</p>
                    </div>
                    <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                      <p className="text-xs text-neutral-500 mb-1">Clusters</p>
                      <p className="text-xl font-bold text-purple-400">{upload.clusters_created || 0}</p>
                    </div>
                  </div>

                  {/* Clusters Preview */}
                  {upload.clusters && upload.clusters.length > 0 && (
                    <div>
                      <div className="flex items-center gap-2 mb-3">
                        <TrendingUp className="w-4 h-4 text-neutral-400" />
                        <h4 className="text-sm font-semibold text-neutral-400 uppercase tracking-wider">
                          Top Issues ({upload.clusters.length})
                        </h4>
                      </div>
                      <div className="space-y-2">
                        {upload.clusters.slice(0, 5).map((cluster) => (
                          <div
                            key={cluster.id}
                            className={`p-2 rounded-lg border flex items-center justify-between ${getSeverityColor(cluster.severity)}`}
                          >
                            <div className="flex items-center gap-2 flex-1 min-w-0">
                              {getSeverityIcon(cluster.severity)}
                              <span className="text-sm font-medium text-white truncate">
                                {cluster.title}
                              </span>
                            </div>
                            <span className="text-xs font-medium whitespace-nowrap ml-2">
                              {cluster.review_count} review{cluster.review_count !== 1 ? 's' : ''}
                            </span>
                          </div>
                        ))}
                        {upload.clusters.length > 5 && (
                          <p className="text-xs text-neutral-500 text-center pt-2">
                            +{upload.clusters.length - 5} more clusters
                          </p>
                        )}
                      </div>
                    </div>
                  )}

                  {/* View Analytics Button */}
                  <div className="mt-4 pt-4 border-t border-white/10">
                    <button
                      onClick={() => router.push(`/analytics?upload_id=${upload.id}`)}
                      className="w-full px-4 py-3 rounded-xl bg-gradient-to-r from-orange-500 to-red-500 hover:from-orange-600 hover:to-red-600 text-white font-medium transition-all hover:shadow-lg hover:shadow-orange-500/25 flex items-center justify-center gap-2"
                    >
                      <TrendingUp className="w-4 h-4" />
                      View Analytics
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </div>
                </>
              )}

              {/* Processing State - Only show when actively processing */}
              {upload.status === 'processing' && (
                <div className="mt-4 pt-4 border-t border-white/10">
                  <div className="grid grid-cols-3 gap-4 mb-4">
                    <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                      <p className="text-xs text-neutral-500 mb-1">Total Reviews</p>
                      <p className="text-xl font-bold text-white">{upload.total_reviews?.toLocaleString() || '...'}</p>
                    </div>
                    <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                      <p className="text-xs text-neutral-500 mb-1">Status</p>
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
                        <p className="text-sm font-medium text-blue-400">Analyzing</p>
                      </div>
                    </div>
                    <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                      <p className="text-xs text-neutral-500 mb-1">Progress</p>
                      <div className="w-full bg-neutral-800 rounded-full h-2 mt-2">
                        <div className="bg-gradient-to-r from-blue-500 to-cyan-500 h-2 rounded-full animate-pulse" style={{width: '60%'}}></div>
                      </div>
                    </div>
                  </div>
                  <p className="text-xs text-center text-neutral-500">Processing may take a few moments depending on dataset size...</p>
                </div>
              )}

              {/* Failed State */}
              {upload.status === 'failed' && (
                <div className="mt-4 pt-4 border-t border-white/10">
                  <div className="p-4 rounded-lg bg-red-500/5 border border-red-500/20 flex items-start gap-3">
                    <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-red-400 mb-1">Processing Failed</p>
                      <p className="text-xs text-neutral-400">There was an error processing this dataset. Please try uploading again.</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Pending State */}
              {upload.status === 'pending' && (
                <div className="mt-4 pt-4 border-t border-white/10">
                  <div className="p-4 rounded-lg bg-neutral-500/5 border border-neutral-500/20 flex items-start gap-3">
                    <Clock className="w-5 h-5 text-neutral-400 flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-neutral-300 mb-1">Queued for Processing</p>
                      <p className="text-xs text-neutral-500">Your dataset is in the queue and will be processed shortly.</p>
                    </div>
                  </div>
                </div>
              )}
            </SpotlightCard>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
