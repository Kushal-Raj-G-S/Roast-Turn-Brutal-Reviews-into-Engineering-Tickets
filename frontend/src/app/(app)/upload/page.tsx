"use client";

/**
 * Upload Page - CSV Dropzone
 * ===========================
 * Features: EmptyState dropzone, upload progress, API integration
 */

import { motion, AnimatePresence } from "framer-motion";
import { useState, useEffect, useRef } from "react";
import {
  Upload,
  FileCheck,
  AlertCircle,
  ArrowRight,
  Loader2,
  Filter,
  Brain,
  Layers,
  BarChart3,
  Bot,
  Sparkles,
  Check,
  Flame,
} from "lucide-react";
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
  isLimitError?: boolean;
  errorCode?: string;
  errorDetails?: any;
}

interface ProgressData {
  upload_id: number;
  status: string;
  stage: string;
  progress: number;
  total: number;
  current: number;
  message: string;
  total_reviews?: number;
  filtered_noise?: number;
  clusters_created?: number;
  error_message?: string;
}

// Real pipeline stages (see backend/app/services/bulk_processor.py +
// explanation_pregenerate.py) mapped to an elapsed-time-based progress
// estimate, since the backend doesn't stream granular percentages — this
// keeps the copy honest about what's actually happening instead of
// inventing generic "processing..." filler.
const STAGES = [
  {
    max: 15,
    label: "Reading & filtering your file",
    detail: "Dropping spam, generic praise, and near-duplicate reviews before any AI touches it.",
    icon: Filter,
  },
  {
    max: 55,
    label: "Understanding what's being said",
    detail: "Every review is embedded locally on this server — no data leaves for this step.",
    icon: Brain,
  },
  {
    max: 78,
    label: "Grouping similar issues together",
    detail: "“Crashes on login” and “freezes when signing in” land in the same cluster, even worded differently.",
    icon: Layers,
  },
  {
    max: 90,
    label: "Ranking by severity",
    detail: "Every cluster gets classified CRITICAL → LOW based on impact and volume.",
    icon: BarChart3,
  },
  {
    max: 100,
    label: "AI is investigating root causes",
    detail: "A multi-step agent hypothesizes, checks past resolved issues, critiques itself, then finalizes each report.",
    icon: Bot,
  },
];

const PROCESSING_TIPS = [
  "Near-identical reviews (“Good app”, “good app”, “GOOD APP”) are deduplicated for free before embedding.",
  "Clusters aren't matched by keyword — they're matched by meaning, using semantic embeddings.",
  "Every CRITICAL/HIGH cluster gets a self-critiquing AI pass, not just a single guess.",
  "Each AI root-cause hypothesis is scored for how well it's actually backed by the reviews.",
  "This batch is checked against your previously resolved issues to catch regressions automatically.",
  "Larger files take longer up front, but you get a full structured breakdown — not just a star average.",
];

// Calibrated from a real local run (15,000 reviews -> ~5.3 min end-to-end
// for noise filtering + local embedding + clustering). This is deliberately
// a rough per-review estimate, not a promise — it exists so the progress
// bar's pace scales with how big the actual file is, instead of a fixed
// time constant that would race ahead of reality on a huge upload (e.g.
// showing 90%+ while embedding alone is still running) or crawl forever on
// a tiny one. `total_reviews` now arrives on the very first poll (backend
// stores the pre-flight row count immediately at upload time), so this is
// available before processing has done any real work.
const MS_PER_REVIEW = 21;
const MIN_ESTIMATE_MS = 20_000;

function estimateTotalMs(totalReviews?: number | null) {
  if (!totalReviews || totalReviews <= 0) return 90_000; // unknown size fallback
  return Math.max(MIN_ESTIMATE_MS, totalReviews * MS_PER_REVIEW);
}

function getStageIndex(pct: number, clustersCreated?: number | null) {
  if (clustersCreated && clustersCreated > 0) return STAGES.length - 1;
  const idx = STAGES.findIndex((s) => pct <= s.max);
  return idx === -1 ? STAGES.length - 1 : idx;
}

function formatElapsed(sec: number) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function UploadPage() {
  const router = useRouter();
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [uploadId, setUploadId] = useState<number | null>(null);
  const [progress, setProgress] = useState<ProgressData | null>(null);
  const pollInterval = useRef<NodeJS.Timeout | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [tipIndex, setTipIndex] = useState(0);
  const startTimeRef = useRef<number | null>(null);

  // Drives the stage tracker + progress bar off wall-clock time, since the
  // backend doesn't stream a granular percentage. Capped short of 100% —
  // the real "done" signal is progress.status === 'completed' elsewhere.
  useEffect(() => {
    if (!isUploading) {
      startTimeRef.current = null;
      setElapsedSec(0);
      return;
    }
    startTimeRef.current = Date.now();
    const tick = setInterval(() => {
      if (startTimeRef.current) {
        setElapsedSec(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }
    }, 1000);
    return () => clearInterval(tick);
  }, [isUploading]);

  useEffect(() => {
    if (!isUploading) {
      setTipIndex(0);
      return;
    }
    const tipTimer = setInterval(() => {
      setTipIndex((i) => (i + 1) % PROCESSING_TIPS.length);
    }, 4000);
    return () => clearInterval(tipTimer);
  }, [isUploading]);

  const tauSec = estimateTotalMs(progress?.total_reviews) / 1000;
  const simulatedProgress = Math.min(96, Math.round(100 * (1 - Math.exp(-elapsedSec / tauSec))));
  const stageIndex = getStageIndex(simulatedProgress, progress?.clusters_created);
  const currentStage = STAGES[stageIndex];

  // Poll for progress updates
  useEffect(() => {
    if (!uploadId || !isUploading) return;

    let consecutiveFailures = 0;
    const MAX_CONSECUTIVE_FAILURES = 10; // ~20s of failures before giving up

    const pollProgress = async () => {
      try {
        // Long jobs (200k+ reviews) can outlive the access token's 1hr
        // lifetime — refresh it before every poll so the token used here
        // never goes stale mid-job (getSession() refreshes if needed).
        const { data: { session } } = await supabase.auth.getSession();
        if (!session) {
          throw new Error("Session expired and could not be refreshed");
        }
        apiClient.setToken(session.access_token);

        const progressData = await apiClient.getUploadProgress(uploadId);
        consecutiveFailures = 0;

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
        consecutiveFailures++;
        if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
          // Session truly can't be refreshed (e.g. logged out elsewhere) —
          // stop hammering the backend. The job itself keeps running
          // server-side regardless; this only stops the UI's progress poll.
          clearInterval(pollInterval.current!);
          console.warn(
            `Progress polling stopped after ${MAX_CONSECUTIVE_FAILURES} consecutive failures. ` +
            "The upload is still processing in the background — reload this page to resume tracking it."
          );
        }
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
      
      // Check if it's a plan limit error (402)
      const isLimitError = error.status === 402 || error.code === 'UPLOAD_LIMIT_REACHED' || error.code === 'REVIEW_LIMIT_EXCEEDED';
      
      setResult({
        success: false,
        message: error.message || "Failed to upload file. Please try again.",
        isLimitError,
        errorCode: error.code,
        errorDetails: error.details,
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
              <div className="relative w-24 h-24 mx-auto mb-6">
                {/* Ambient embers drifting up around the icon — purely
                    decorative, on-brand with the Roast fire theme */}
                {[0, 1, 2, 3, 4].map((i) => (
                  <motion.span
                    key={i}
                    className="absolute bottom-2 w-1 h-1 rounded-full bg-orange-400"
                    style={{ left: `${12 + i * 18}%` }}
                    animate={{
                      y: [0, -70 - i * 6],
                      opacity: [0, 0.9, 0],
                      scale: [0.6, 1, 0.4],
                    }}
                    transition={{
                      duration: 2.4 + i * 0.35,
                      repeat: Infinity,
                      delay: i * 0.5,
                      ease: "easeOut",
                    }}
                  />
                ))}
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
                  className="absolute inset-0 rounded-full border-2 border-dashed border-orange-500/30"
                />
                <div className="absolute inset-2 rounded-3xl bg-gradient-to-br from-orange-500 to-red-600 flex items-center justify-center shadow-lg shadow-orange-500/30 overflow-hidden">
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={currentStage.label}
                      initial={{ opacity: 0, scale: 0.5, rotate: -90 }}
                      animate={{ opacity: 1, scale: 1, rotate: 0 }}
                      exit={{ opacity: 0, scale: 0.5, rotate: 90 }}
                      transition={{ duration: 0.4 }}
                    >
                      <currentStage.icon className="w-9 h-9 text-white" />
                    </motion.div>
                  </AnimatePresence>
                </div>
              </div>

              <AnimatePresence mode="wait">
                <motion.div
                  key={currentStage.label}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.3 }}
                >
                  <h2 className="text-2xl font-bold text-white mb-2 flex items-center justify-center gap-2">
                    {currentStage.label}
                    <span className="inline-flex gap-0.5">
                      {STAGES.map((_, i) => (
                        <Flame
                          key={i}
                          className={`w-4 h-4 transition-colors ${
                            i <= stageIndex ? "text-orange-500 fill-orange-500" : "text-white/10"
                          }`}
                        />
                      ))}
                    </span>
                  </h2>
                  <p className="text-neutral-400 mb-6 max-w-md mx-auto">
                    {currentStage.detail}
                  </p>
                </motion.div>
              </AnimatePresence>

              {/* Step checklist */}
              <div className="flex items-center max-w-md mx-auto mb-6">
                {STAGES.map((s, i) => {
                  const done = i < stageIndex;
                  const active = i === stageIndex;
                  return (
                    <div key={s.label} className="flex items-center flex-1 last:flex-none">
                      <div
                        title={s.label}
                        className={`relative w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 border-2 transition-colors duration-300 ${
                          done
                            ? "bg-emerald-500 border-emerald-500"
                            : active
                              ? "border-orange-500 bg-orange-500/10"
                              : "border-white/10 bg-white/5"
                        }`}
                      >
                        {done ? (
                          <Check className="w-3.5 h-3.5 text-white" />
                        ) : active ? (
                          <motion.div
                            animate={{ scale: [1, 1.4, 1] }}
                            transition={{ duration: 1.2, repeat: Infinity }}
                            className="w-2 h-2 rounded-full bg-orange-500"
                          />
                        ) : (
                          <div className="w-1.5 h-1.5 rounded-full bg-white/20" />
                        )}
                      </div>
                      {i < STAGES.length - 1 && (
                        <div
                          className={`h-0.5 flex-1 mx-1 rounded transition-colors duration-500 ${
                            done ? "bg-emerald-500" : "bg-white/10"
                          }`}
                        />
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Review Stats */}
              <div className="grid grid-cols-3 gap-4 max-w-md mx-auto mb-6">
                <div className="text-center">
                  <div className="text-2xl font-bold text-white">
                    {progress.total_reviews ? progress.total_reviews.toLocaleString() : "—"}
                  </div>
                  <div className="text-xs text-neutral-500">Total Reviews</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-orange-400">
                    {progress.total_reviews
                      ? (progress.total_reviews - (progress.filtered_noise || 0)).toLocaleString()
                      : "—"}
                  </div>
                  <div className="text-xs text-neutral-500">Kept</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-emerald-400">
                    {progress.clusters_created ?? "—"}
                  </div>
                  <div className="text-xs text-neutral-500">Clusters</div>
                </div>
              </div>

              {/* Progress Bar */}
              <div className="max-w-md mx-auto mb-6">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-neutral-400">{formatElapsed(elapsedSec)} elapsed</span>
                  <span className="text-sm font-bold text-orange-400">{simulatedProgress}%</span>
                </div>
                <div className="h-3 rounded-full bg-white/5 overflow-hidden">
                  <motion.div
                    className="h-full bg-gradient-to-r from-orange-500 to-red-600 rounded-full"
                    animate={{ width: `${simulatedProgress}%` }}
                    transition={{ duration: 0.8, ease: "easeOut" }}
                  />
                </div>
              </div>

              {/* Rotating tip ticker */}
              <div className="max-w-md mx-auto mb-4 min-h-[52px] flex items-center justify-center px-4 py-3 rounded-xl bg-white/5 border border-white/10">
                <Sparkles className="w-4 h-4 text-orange-400 flex-shrink-0 mr-2" />
                <AnimatePresence mode="wait">
                  <motion.p
                    key={tipIndex}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.3 }}
                    className="text-xs text-neutral-400 text-left"
                  >
                    {PROCESSING_TIPS[tipIndex]}
                  </motion.p>
                </AnimatePresence>
              </div>

              <p className="text-xs text-neutral-600">
                You can leave this page and come back later — processing continues in the background.
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
                  {/* Plan Limit Error - Special UI */}
                  {result.isLimitError ? (
                    <>
                      <motion.div
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        transition={{ type: "spring", stiffness: 200, damping: 15 }}
                        className="w-20 h-20 rounded-3xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center mx-auto mb-6 shadow-lg shadow-amber-500/30"
                      >
                        <AlertCircle className="w-10 h-10 text-white" />
                      </motion.div>

                      <h2 className="text-2xl font-bold text-white mb-2">
                        {result.errorCode === 'REVIEW_LIMIT_EXCEEDED' ? 'File Too Large' : 'Upload Limit Reached'}
                      </h2>
                      <p className="text-neutral-400 mb-6">{result.message}</p>

                      {/* Limit Details */}
                      {result.errorDetails && (
                        <div className="max-w-md mx-auto mb-8 p-4 rounded-xl bg-neutral-900/50 border border-neutral-800">
                          <div className="grid grid-cols-2 gap-4 text-sm">
                            {result.errorDetails.uploads_used !== undefined && (
                              <>
                                <div className="text-neutral-500">Used this month:</div>
                                <div className="text-white font-semibold">{result.errorDetails.uploads_used}/{result.errorDetails.uploads_limit}</div>
                              </>
                            )}
                            {result.errorDetails.row_count && (
                              <>
                                <div className="text-neutral-500">File rows:</div>
                                <div className="text-white font-semibold">{result.errorDetails.row_count.toLocaleString()}</div>
                                <div className="text-neutral-500">Plan limit:</div>
                                <div className="text-white font-semibold">{result.errorDetails.reviews_limit.toLocaleString()}</div>
                              </>
                            )}
                            <div className="text-neutral-500">Current plan:</div>
                            <div className="text-orange-400 font-semibold capitalize">{result.errorDetails.plan}</div>
                          </div>
                        </div>
                      )}

                      <div className="flex items-center justify-center gap-4">
                        <Link
                          href="/pricing"
                          className="px-6 py-3 rounded-xl bg-gradient-to-r from-orange-500 to-red-600 text-white font-semibold hover:shadow-lg hover:shadow-orange-500/25 transition-all"
                        >
                          Upgrade Plan
                        </Link>
                        <button
                          onClick={resetUpload}
                          className="px-6 py-3 rounded-xl border border-white/10 text-white font-semibold hover:bg-white/5 transition-colors"
                        >
                          Go Back
                        </button>
                      </div>
                    </>
                  ) : (
                    /* Generic Error */
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
