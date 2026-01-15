"use client";

/**
 * Upload Page - CSV Dropzone
 * ===========================
 * Features: EmptyState dropzone, upload progress, API integration
 */

import { motion } from "framer-motion";
import { useState } from "react";
import { Upload, FileCheck, AlertCircle, ArrowRight } from "lucide-react";
import { EmptyState } from "@/components/ui";
import { SpotlightCard } from "@/components/ui";
import Link from "next/link";

interface UploadResult {
  success: boolean;
  message: string;
  stats?: {
    total_reviews: number;
    clusters_created: number;
    tickets_generated: number;
  };
}

export default function UploadPage() {
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);

  const handleFileSelect = async (file: File) => {
    setIsUploading(true);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      // TODO: Replace with actual API endpoint
      // const response = await fetch("http://localhost:8000/ingest", {
      //   method: "POST",
      //   body: formData,
      // });
      // const data = await response.json();

      // Simulate API call
      await new Promise((resolve) => setTimeout(resolve, 3000));

      // Mock success result
      setResult({
        success: true,
        message: "Reviews processed successfully!",
        stats: {
          total_reviews: 1247,
          clusters_created: 23,
          tickets_generated: 23,
        },
      });
    } catch (error) {
      setResult({
        success: false,
        message: "Failed to process file. Please try again.",
      });
    } finally {
      setIsUploading(false);
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
        {result ? (
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
                    Your reviews have been processed and tickets are ready.
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
