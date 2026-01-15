"use client";

/**
 * Analytics Page - Review Analytics Dashboard
 * ============================================
 * Insights and metrics from roasted reviews
 */

import { motion } from "framer-motion";
import { BarChart3, TrendingUp, PieChart } from "lucide-react";

export default function AnalyticsPage() {
  return (
    <div className="space-y-6">
      {/* Page Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-2xl font-bold text-white">Analytics</h1>
        <p className="text-neutral-500">Insights and trends from your reviews</p>
      </motion.div>

      {/* Coming Soon Card */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="flex items-center justify-center min-h-[60vh]"
      >
        <div className="text-center max-w-md">
          <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-blue-500/20 to-cyan-500/20 border border-blue-500/20 flex items-center justify-center">
            <BarChart3 className="w-10 h-10 text-blue-400" />
          </div>
          <h2 className="text-2xl font-bold text-white mb-3">Advanced Analytics</h2>
          <p className="text-neutral-400 mb-6">
            Get deep insights into review patterns, sentiment trends, and performance metrics. 
            Visual dashboards coming soon!
          </p>
          <div className="flex flex-wrap justify-center gap-4 text-sm text-neutral-500">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-4 h-4" />
              <span>Trend Analysis</span>
            </div>
            <div className="flex items-center gap-2">
              <TrendingUp className="w-4 h-4" />
              <span>Performance Metrics</span>
            </div>
            <div className="flex items-center gap-2">
              <PieChart className="w-4 h-4" />
              <span>Sentiment Distribution</span>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
