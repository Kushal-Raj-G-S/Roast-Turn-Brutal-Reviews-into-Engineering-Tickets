"use client";

/**
 * Clusters Page - Review Clustering View
 * =======================================
 * Shows grouped reviews by similarity
 */

import { motion } from "framer-motion";
import { Layers, TrendingUp, Users } from "lucide-react";

export default function ClustersPage() {
  return (
    <div className="space-y-6">
      {/* Page Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-2xl font-bold text-white">Clusters</h1>
        <p className="text-neutral-500">AI-grouped reviews by similarity</p>
      </motion.div>

      {/* Coming Soon Card */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="flex items-center justify-center min-h-[60vh]"
      >
        <div className="text-center max-w-md">
          <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-orange-500/20 to-red-500/20 border border-orange-500/20 flex items-center justify-center">
            <Layers className="w-10 h-10 text-orange-400" />
          </div>
          <h2 className="text-2xl font-bold text-white mb-3">Review Clustering</h2>
          <p className="text-neutral-400 mb-6">
            Automatically group similar reviews together using AI-powered semantic analysis. 
            This feature is coming soon!
          </p>
          <div className="flex flex-wrap justify-center gap-4 text-sm text-neutral-500">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-4 h-4" />
              <span>Smart Grouping</span>
            </div>
            <div className="flex items-center gap-2">
              <Users className="w-4 h-4" />
              <span>Pattern Detection</span>
            </div>
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4" />
              <span>Auto-categorization</span>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
