"use client";

/**
 * Clusters Page - Review Clustering View
 * =======================================
 * Shows grouped reviews by similarity from backend API
 */

import { motion } from "framer-motion";
import { Layers, AlertCircle, CheckCircle2, Clock, Flame } from "lucide-react";
import { useEffect, useState } from "react";
import { apiClient, Upload, Cluster } from "@/lib/api-client";
import { supabase } from "@/lib/supabase/client";
import Link from "next/link";

export default function ClustersPage() {
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [selectedUpload, setSelectedUpload] = useState<Upload | null>(null);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchUploads();
  }, []);

  const fetchUploads = async () => {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) return;

      apiClient.setToken(session.access_token);
      const uploadsData = await apiClient.getUploads();
      setUploads(uploadsData);
      
      if (uploadsData.length > 0) {
        setSelectedUpload(uploadsData[0]);
        fetchClusters(uploadsData[0].id);
      }
      
      setLoading(false);
    } catch (error) {
      console.error('Error fetching uploads:', error);
      setLoading(false);
    }
  };

  const fetchClusters = async (uploadId: number) => {
    try {
      const clustersData = await apiClient.getUploadClusters(uploadId);
      setClusters(clustersData);
    } catch (error) {
      console.error('Error fetching clusters:', error);
    }
  };

  const handleUploadSelect = (upload: Upload) => {
    setSelectedUpload(upload);
    fetchClusters(upload.id);
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'text-red-400 border-red-500/50 bg-red-500/10';
      case 'high': return 'text-orange-400 border-orange-500/50 bg-orange-500/10';
      case 'medium': return 'text-yellow-400 border-yellow-500/50 bg-yellow-500/10';
      case 'low': return 'text-blue-400 border-blue-500/50 bg-blue-500/10';
      default: return 'text-neutral-400 border-neutral-500/50 bg-neutral-500/10';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'fresh_roast': return <Flame className="w-4 h-4" />;
      case 'in_progress': return <Clock className="w-4 h-4" />;
      case 'resolved': return <CheckCircle2 className="w-4 h-4" />;
      default: return <AlertCircle className="w-4 h-4" />;
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <div className="animate-spin w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full mx-auto mb-4"></div>
          <p className="text-neutral-400">Loading clusters...</p>
        </div>
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
        <h1 className="text-2xl font-bold text-white">Issue Clusters</h1>
        <p className="text-neutral-500">AI-grouped reviews by similarity</p>
      </motion.div>

      {/* Upload Selector */}
      {uploads.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex gap-2 overflow-x-auto pb-2"
        >
          {uploads.map((upload) => (
            <button
              key={upload.id}
              onClick={() => handleUploadSelect(upload)}
              className={`px-4 py-2 rounded-lg border whitespace-nowrap transition-all ${
                selectedUpload?.id === upload.id
                  ? 'bg-orange-500/20 border-orange-500 text-orange-400'
                  : 'bg-neutral-900/50 border-neutral-800 text-neutral-400 hover:border-neutral-700'
              }`}
            >
              {upload.filename} ({upload.clusters_created} clusters)
            </button>
          ))}
        </motion.div>
      )}

      {/* Clusters Grid */}
      {clusters.length > 0 ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
        >
          {clusters.map((cluster, index) => (
            <motion.div
              key={cluster.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05 }}
            >
              <Link href={`/clusters/${cluster.id}`}>
                <div className="p-5 rounded-xl bg-neutral-900/50 border border-neutral-800 hover:border-neutral-700 transition-all group cursor-pointer">
                  <div className="flex items-start justify-between mb-3">
                    <div className={`px-2 py-1 rounded-lg border text-xs font-medium ${getSeverityColor(cluster.severity)}`}>
                      {cluster.severity.toUpperCase()}
                    </div>
                    <div className="flex items-center gap-1 text-neutral-400">
                      {getStatusIcon(cluster.status)}
                    </div>
                  </div>
                  
                  <h3 className="text-white font-semibold mb-2 group-hover:text-orange-400 transition-colors">
                    {cluster.title}
                  </h3>
                  
                  <div className="flex items-center gap-4 text-sm text-neutral-500">
                    <span>{cluster.review_count} reviews</span>
                    <span>•</span>
                    <span>{cluster.cluster_uuid.slice(0, 8)}</span>
                  </div>
                </div>
              </Link>
            </motion.div>
          ))}
        </motion.div>
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center justify-center min-h-[40vh]"
        >
          <div className="text-center max-w-md">
            <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-orange-500/20 to-red-500/20 border border-orange-500/20 flex items-center justify-center">
              <Layers className="w-10 h-10 text-orange-400" />
            </div>
            <h2 className="text-2xl font-bold text-white mb-3">No Clusters Yet</h2>
            <p className="text-neutral-400 mb-6">
              Upload a CSV file to start analyzing reviews and creating issue clusters.
            </p>
            <Link
              href="/upload"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-orange-500 to-red-600 text-white font-semibold hover:shadow-lg hover:shadow-orange-500/25 transition-all"
            >
              Upload Reviews
            </Link>
          </div>
        </motion.div>
      )}
    </div>
  );
}
