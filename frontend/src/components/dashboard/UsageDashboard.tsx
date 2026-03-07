"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase/client";
import { Upload, Calendar, TrendingUp, Clock } from "lucide-react";

interface UserPlan {
  plan: string;
  label: string;
  uploads_used: number;
  uploads_limit: number | null;
  reviews_limit: number | null;
  reset_date: string;
}

export function UsageDashboard() {
  const [planData, setPlanData] = useState<UserPlan | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchPlanData = async () => {
      try {
        const { data: session } = await supabase.auth.getSession();
        if (session.session?.access_token) {
          const response = await fetch('/api/proxy/user/plan', {
            headers: {
              'Authorization': `Bearer ${session.session.access_token}`,
              'Content-Type': 'application/json',
            },
          });
          if (response.ok) {
            const data = await response.json();
            setPlanData(data);
          }
        }
      } catch (error) {
        console.error('Failed to fetch plan data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchPlanData();
  }, []);

  if (loading) {
    return (
      <div className="bg-neutral-900/50 border border-neutral-800 rounded-2xl p-6">
        <div className="animate-pulse">
          <div className="h-6 w-32 bg-neutral-700 rounded mb-4" />
          <div className="space-y-3">
            <div className="h-4 w-full bg-neutral-700 rounded" />
            <div className="h-4 w-3/4 bg-neutral-700 rounded" />
          </div>
        </div>
      </div>
    );
  }

  if (!planData) {
    return (
      <div className="bg-neutral-900/50 border border-neutral-800 rounded-2xl p-6">
        <p className="text-neutral-400">Unable to load usage data</p>
      </div>
    );
  }

  const uploadProgress = planData.uploads_limit 
    ? (planData.uploads_used / planData.uploads_limit) * 100 
    : 0;

  const isNearLimit = uploadProgress > 80;
  const isAtLimit = planData.uploads_limit && planData.uploads_used >= planData.uploads_limit;

  const resetDate = new Date(planData.reset_date);
  const daysUntilReset = Math.ceil((resetDate.getTime() - Date.now()) / (1000 * 60 * 60 * 24));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-bold text-white">Usage & Plan</h3>
        <span className={`px-3 py-1 text-sm font-medium rounded-full ${
          planData.plan === 'pro' ? 'text-orange-400 bg-orange-500/10' :
          planData.plan === 'business' ? 'text-purple-400 bg-purple-500/10' :
          planData.plan === 'enterprise' ? 'text-blue-400 bg-blue-500/10' :
          planData.plan === 'starter' ? 'text-green-400 bg-green-500/10' :
          'text-neutral-400 bg-neutral-800'
        }`}>
          {planData.label} Plan
        </span>
      </div>

      {/* Current Month Usage */}
      <motion.div
        className="bg-neutral-900/50 border border-neutral-800 rounded-2xl p-6"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-500/10 rounded-lg">
              <Upload className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <h4 className="font-semibold text-white">Monthly Uploads</h4>
              <p className="text-sm text-neutral-400">This month's usage</p>
            </div>
          </div>
          <div className="text-right">
            {planData.uploads_limit ? (
              <div className="text-2xl font-bold text-white">
                {planData.uploads_used}
                <span className="text-lg text-neutral-400">/{planData.uploads_limit}</span>
              </div>
            ) : (
              <div className="text-2xl font-bold text-white">
                {planData.uploads_used}
                <span className="text-lg text-neutral-400">/∞</span>
              </div>
            )}
          </div>
        </div>

        {planData.uploads_limit && (
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-neutral-400">Progress</span>
              <span className={`font-medium ${
                isAtLimit ? 'text-red-400' : 
                isNearLimit ? 'text-orange-400' : 
                'text-green-400'
              }`}>
                {Math.round(uploadProgress)}%
              </span>
            </div>
            <div className="w-full h-2 bg-neutral-800 rounded-full overflow-hidden">
              <motion.div
                className={`h-full rounded-full ${
                  isAtLimit ? 'bg-red-500' :
                  isNearLimit ? 'bg-orange-500' :
                  'bg-green-500'
                }`}
                initial={{ width: 0 }}
                animate={{ width: `${Math.min(uploadProgress, 100)}%` }}
                transition={{ duration: 1, delay: 0.2 }}
              />
            </div>
            {isAtLimit && (
              <p className="text-sm text-red-400 mt-2">
                Upload limit reached. Upgrade to continue uploading.
              </p>
            )}
            {isNearLimit && !isAtLimit && (
              <p className="text-sm text-orange-400 mt-2">
                Approaching monthly limit. Consider upgrading.
              </p>
            )}
          </div>
        )}
      </motion.div>

      {/* Plan Details */}
      <motion.div
        className="bg-neutral-900/50 border border-neutral-800 rounded-2xl p-6"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.1 }}
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          {/* Review Limit */}
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-500/10 rounded-lg">
              <TrendingUp className="w-5 h-5 text-green-400" />
            </div>
            <div>
              <p className="text-sm text-neutral-400">Reviews per upload</p>
              <p className="font-semibold text-white">
                {planData.reviews_limit ? planData.reviews_limit.toLocaleString() : 'Unlimited'}
              </p>
            </div>
          </div>

          {/* Reset Date */}
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-500/10 rounded-lg">
              <Calendar className="w-5 h-5 text-purple-400" />
            </div>
            <div>
              <p className="text-sm text-neutral-400">Resets in</p>
              <p className="font-semibold text-white">
                {daysUntilReset} day{daysUntilReset !== 1 ? 's' : ''}
              </p>
            </div>
          </div>
        </div>

        {planData.plan === 'free' && (
          <div className="mt-6 p-4 bg-gradient-to-r from-orange-500/10 to-red-600/10 border border-orange-500/20 rounded-xl">
            <p className="text-sm text-orange-200 mb-2">
              🔥 Need more uploads?
            </p>
            <p className="text-xs text-neutral-400 mb-3">
              Upgrade to Starter for 10 uploads/month or Pro for 50 uploads/month.
            </p>
            <button className="text-xs bg-gradient-to-r from-orange-500 to-red-600 text-white px-3 py-1 rounded-full hover:opacity-90 transition-opacity">
              View Plans
            </button>
          </div>
        )}
      </motion.div>
    </div>
  );
}