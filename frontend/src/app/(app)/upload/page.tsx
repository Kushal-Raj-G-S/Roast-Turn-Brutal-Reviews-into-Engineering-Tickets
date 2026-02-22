"use client";

/**
 * Upload Page - CSV Dropzone
 * ===========================
 * Features: EmptyState dropzone, upload progress, API integration
 */

import { motion } from "framer-motion";
import { useState, useEffect, useRef } from "react";
import { Upload, FileCheck, AlertCircle, ArrowRight, Loader2 } from "lucide-react";
import { EmptyState } from "@/components/ui";
import { SpotlightCard } from "@/components/ui";
import Link from "next/link";
import { apiClient } from "@/lib/api-client";
import { supabase } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";

interface UploadResult {
  success: boolean;
  message: string;
  stats?: {
    total_reviews: number;
    clusters_created: number;
    tickets_generated: number;
  };
}

interface ProgressData {
  upload_id: number;
  status: string;
  stage: string;
  progress: number;
  total: number;
  current: number;
  message: string;
}

export default function UploadPage() {
  const router = useRouter();
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [uploadId, setUploadId] = useState<number | null>(null);
  const [progress, setProgress] = useState<ProgressData | null>(null);
  const pollInterval = useRef<NodeJS.Timeout | null>(null);

  // Poll for progress updates
  useEffect(() => {
    if (!uploadId || !isUploading) return;

    const pollProgress = async () => {
      try {
        const progressData = await apiClient.getUploadProgress(uploadId);
        
        if (progressData) {
          setProgress(progressData);
          
          // Stop polling if completed or failed
          if (progressData.status === 'completed') {
            clearInterval(pollInterval.current!);
            setIsUploading(false);
            
            // Immediately redirect to analytics page without showing success screen
            router.push(`/analytics?upload_id=${uploadId}`);
          } else if (progressData.status === 'failed') {
            clearInterval(pollInterval.current!);
            setIsUploading(false);
            setResult({
              success: false,
              message: progressData.error_message || "Processing failed",
            });
          }
        }
      } catch (error) {
        console.error('Error polling progress:', error);
      }
    };

    // Poll every 2 seconds
    pollInterval.current = setInterval(pollProgress, 2000);
    pollProgress(); // Initial poll

    return () => {
      if (pollInterval.current) {
        clearInterval(pollInterval.current);
      }
    };
  }, [uploadId, isUploading, router]);

  const handleFileSelect = async (file: File) => {
    setIsUploading(true);
    setResult(null);
    setProgress(null);

    try {
      // Get Supabase session token
      const { data: { session } } = await supabase.auth.getSession();
      
      if (!session) {
        throw new Error("Please log in to upload files");
      }

      // Set the token for API client
      apiClient.setToken(session.access_token);

      // Upload to backend API (returns immediately with upload record)
      const upload = await apiClient.uploadCSV(file);
      
      // Start polling for progress - use upload_id from response
      setUploadId(upload.upload_id);
      setProgress({
        upload_id: upload.upload_id,
        status: 'processing',
        stage: 'starting',
        progress: 0,
        total: 0,
        current: 0,
        message: 'Starting to process reviews...'
      });

    } catch (error: any) {
      setIsUploading(false);
      setResult({
        success: false,
        message: error.message || "Failed to upload file. Please try again.",
      });
    }
  };

  const resetUpload = () => {
    setResult(null);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Page Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-2xl font-bold text-white">Upload Reviews</h1>
        <p className="text-neutral-500">
          Import your CSV file and let AI create actionable tickets
        </p>
      </motion.div>

      {/* Main Content */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        {isUploading && progress ? (
          // Progress Card
          <SpotlightCard className="p-8">
            <div className="text-center">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                className="w-20 h-20 rounded-3xl bg-gradient-to-br from-orange-500 to-red-600 flex items-center justify-center mx-auto mb-6 shadow-lg shadow-orange-500/30"
              >
                <Loader2 className="w-10 h-10 text-white" />
              </motion.div>

              <h2 className="text-2xl font-bold text-white mb-2">
                Processing Your Reviews
              </h2>
              <p className="text-neutral-400 mb-6">
                {progress.message}
              </p>

              {/* Review Stats */}
              {progress.total_reviews && (
                <div className="grid grid-cols-3 gap-4 max-w-md mx-auto mb-6">
                  <div className="text-center">
                    <div className="text-2xl font-bold text-white">
                      {progress.total_reviews.toLocaleString()}
                    </div>
                    <div className="text-xs text-neutral-500">Total Reviews</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-orange-400">
                      {(progress.total_reviews - (progress.filtered_noise || 0)).toLocaleString()}
                    </div>
                    <div className="text-xs text-neutral-500">Kept</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-emerald-400">
                      {progress.clusters_created || 0}
                    </div>
                    <div className="text-xs text-neutral-500">Clusters</div>
                  </div>
                </div>
              )}

              {/* Progress Bar */}
              <div className="max-w-md mx-auto mb-6">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-neutral-400">{progress.stage}</span>
                  <span className="text-sm font-bold text-orange-400">{progress.progress}%</span>
                </div>
                <div className="h-3 rounded-full bg-white/5 overflow-hidden">
                  <motion.div
                    className="h-full bg-gradient-to-r from-orange-500 to-red-600 rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${progress.progress}%` }}
                    transition={{ duration: 0.5 }}
                  />
                </div>
              </div>

              <p className="text-xs text-neutral-600">
                This may take a few minutes. You can leave this page and come back later.
              </p>
            </div>
          </SpotlightCard>
        ) : result ? (
          // Result Card
          <SpotlightCard className="p-8">
            <div className="text-center">
              {result.success ? (
                <>
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ type: "spring", stiffness: 200, damping: 15 }}
                    className="w-20 h-20 rounded-3xl bg-gradient-to-br from-emerald-500 to-green-600 flex items-center justify-center mx-auto mb-6 shadow-lg shadow-emerald-500/30"
                  >
                    <FileCheck className="w-10 h-10 text-white" />
                  </motion.div>

                  <h2 className="text-2xl font-bold text-white mb-2">
                    {result.message}
                  </h2>
                  <p className="text-neutral-400 mb-8">
                    Redirecting to analytics dashboard...
                  </p>

                  {result.stats && (
                    <div className="grid grid-cols-3 gap-6 max-w-md mx-auto mb-8">
                      <div className="text-center">
                        <div className="text-3xl font-black text-white">
                          {result.stats.total_reviews.toLocaleString()}
                        </div>
                        <div className="text-sm text-neutral-500">Reviews</div>
                      </div>
                      <div className="text-center">
                        <div className="text-3xl font-black text-white">
                          {result.stats.clusters_created}
                        </div>
                        <div className="text-sm text-neutral-500">Clusters</div>
                      </div>
                      <div className="text-center">
                        <div className="text-3xl font-black text-orange-400">
                          {result.stats.tickets_generated}
                        </div>
                        <div className="text-sm text-neutral-500">Tickets</div>
                      </div>
                    </div>
                  )}

                  <div className="flex items-center justify-center gap-4">
                    <Link
                      href="/dashboard"
                      className="flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-orange-500 to-red-600 text-white font-semibold hover:shadow-lg hover:shadow-orange-500/25 transition-all"
                    >
                      View Dashboard
                      <ArrowRight className="w-5 h-5" />
                    </Link>
                    <button
                      onClick={resetUpload}
                      className="px-6 py-3 rounded-xl border border-white/10 text-white font-semibold hover:bg-white/5 transition-colors"
                    >
                      Upload Another
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ type: "spring", stiffness: 200, damping: 15 }}
                    className="w-20 h-20 rounded-3xl bg-gradient-to-br from-red-500 to-pink-600 flex items-center justify-center mx-auto mb-6 shadow-lg shadow-red-500/30"
                  >
                    <AlertCircle className="w-10 h-10 text-white" />
                  </motion.div>

                  <h2 className="text-2xl font-bold text-white mb-2">
                    Upload Failed
                  </h2>
                  <p className="text-neutral-400 mb-8">{result.message}</p>

                  <button
                    onClick={resetUpload}
                    className="px-6 py-3 rounded-xl bg-gradient-to-r from-orange-500 to-red-600 text-white font-semibold hover:shadow-lg hover:shadow-orange-500/25 transition-all"
                  >
                    Try Again
                  </button>
                </>
              )}
            </div>
          </SpotlightCard>
        ) : (
          // Upload Dropzone
          <EmptyState onFileSelect={handleFileSelect} isLoading={isUploading} />
        )}
      </motion.div>

      {/* Help Section */}
      {!result && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <SpotlightCard className="p-6">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500/20 to-cyan-500/20 border border-blue-500/20 flex items-center justify-center flex-shrink-0">
                <Upload className="w-6 h-6 text-blue-400" />
              </div>
              <div>
                <h3 className="font-bold text-white mb-2">CSV Format Guide</h3>
                <p className="text-sm text-neutral-400 mb-4">
                  Your CSV file should include the following columns for best results:
                </p>
                <div className="flex flex-wrap gap-2">
                  {["review_text", "rating", "date", "app_version", "device_type"].map(
                    (col) => (
                      <span
                        key={col}
                        className="px-3 py-1 rounded-lg bg-white/5 text-xs font-mono text-neutral-300"
                      >
                        {col}
                      </span>
                    )
                  )}
                </div>
              </div>
            </div>
          </SpotlightCard>
        </motion.div>
      )}
    </div>
  );
}
