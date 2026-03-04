"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import {
  Sparkles,
  Code2,
  Copy,
  CheckCircle2,
  AlertTriangle,
  AlertCircleIcon,
  Info,
  Star,
  Loader2,
  Brain,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { supabase } from "@/lib/supabase/client";

// ------------------------------------------------------------------ types ---

interface Review {
  content: string;
  rating?: number;
  date?: string;
  version?: string;
  device?: string;
}

interface Cluster {
  id: number;
  cluster_uuid: string;
  title: string;
  severity: "critical" | "high" | "medium" | "low";
  status: string;
  review_count: number;
  sample_reviews?: Review[];
  affected_versions?: string[];
  affected_devices?: string[];
  keywords?: string[];
  created_at: string;
}

interface CategoryExplanation {
  status: "not_started" | "pending" | "generating" | "done" | "failed";
  explanation?: string;
}

// ---------------------------------------------------------------- constants --

const BACKEND = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const SEV = {
  critical: {
    color: "text-red-400",
    bg: "bg-red-500/8",
    border: "border-red-500/20",
    dot: "bg-red-500",
    divider: "divide-red-500/10",
    label: "CRITICAL",
  },
  high: {
    color: "text-orange-400",
    bg: "bg-orange-500/8",
    border: "border-orange-500/20",
    dot: "bg-orange-500",
    divider: "divide-orange-500/10",
    label: "HIGH",
  },
  medium: {
    color: "text-yellow-400",
    bg: "bg-yellow-500/8",
    border: "border-yellow-500/20",
    dot: "bg-yellow-500",
    divider: "divide-yellow-500/10",
    label: "MEDIUM",
  },
  low: {
    color: "text-blue-400",
    bg: "bg-blue-500/8",
    border: "border-blue-500/20",
    dot: "bg-blue-500",
    divider: "divide-blue-500/10",
    label: "LOW",
  },
} as const;

const SEV_TITLE: Record<string, string> = {
  critical: "Critical Issues",
  high: "High Priority Issues",
  medium: "Medium Priority Issues",
  low: "Low Priority Issues",
};

const STATUS_EMOJI: Record<string, string> = {
  fresh_roast: "🔥",
  assigned: "👤",
  in_progress: "🔄",
  resolved: "✅",
  wont_fix: "🚫",
};

const SEVERITIES = ["critical", "high", "medium", "low"] as const;
type SeverityKey = (typeof SEVERITIES)[number];

function cleanTitle(t: string) {
  return t
    .replace(/^\[(CRITICAL|HIGH|MEDIUM|LOW)\]\s*(Issue:\s*)?/i, "")
    .replace(/^Issue:\s*/i, "")
    .trim();
}

function inferPlatform(reviews: Review[]): string {
  let ios = 0, android = 0;
  for (const r of reviews) {
    const d = (r.device || "").toLowerCase();
    if (/iphone|ipad|ios/.test(d)) ios++;
    if (/android|samsung|pixel|huawei|xiaomi/.test(d)) android++;
  }
  if (ios > 0 && android > 0) return "both";
  if (ios > 0) return "ios";
  if (android > 0) return "android";
  return "unknown";
}

function inferFeatureFlow(title: string): string {
  const t = title.toLowerCase();
  if (/playlist|album|library/.test(t)) return "playlist / library";
  if (/playback|play|pause|skip|song|music|audio|stream/.test(t)) return "playback";
  if (/premium|subscription|payment|billing|purchase/.test(t)) return "premium / monetization";
  if (/login|sign.?in|sign.?up|account|auth/.test(t)) return "authentication / account";
  if (/ads?|advert/.test(t)) return "ads";
  if (/crash|freeze|hang|not.?open/.test(t)) return "app stability";
  if (/slow|lag|performance|battery|cpu/.test(t)) return "performance";
  if (/notif/.test(t)) return "notifications";
  if (/download|offline/.test(t)) return "offline / downloads";
  if (/search/.test(t)) return "search";
  if (/ui|design|layout|screen/.test(t)) return "UI / layout";
  return "unknown";
}

function buildRCAPrompt(c: Cluster, appName: string): string {
  const reviews = (c.sample_reviews || []).slice(0, 5);
  const title = cleanTitle(c.title);
  const sevLabel = c.severity.toUpperCase() as string;
  const platform = inferPlatform(reviews);
  const featureFlow = inferFeatureFlow(title);

  const evidenceLines = reviews
    .map((r, i) => {
      const lines = [`[${i + 1}] Rating: ${r.rating ?? "?"}★`];
      if (r.version) lines.push(`     Version: ${r.version}`);
      if (r.device)  lines.push(`     Device:  ${r.device}`);
      lines.push(`     "${r.content.substring(0, 200).trim()}"`);
      return lines.join("\n");
    })
    .join("\n\n");

  return `ROLE
You are a senior mobile / full-stack engineer performing a root cause analysis (RCA) on production app issues surfaced from app store reviews. You are technical, direct, and specific.

CONSTRAINTS
- Every section and every field below MUST be filled. If you cannot infer a value, write exactly: "Unknown – need more data" and state what extra data would resolve it.
- Never leave a bullet point empty or use placeholder text like "…".
- Do NOT invent specific module or service names (e.g. "VideoCacheManager", "RecommendationService") unless directly named or strongly implied by the evidence. Use generic descriptions such as "video playback pipeline" only when clearly hinted.
- Ground every claim in the Evidence section. No speculation beyond what the reviews support.
- severity_assessment MUST be returned in section 1 every time — even when you agree with the input label.
- If feature/flow is "performance" or "ads", default scope to client-side unless the evidence explicitly points to backend.

---

## RCA INPUT

Context:
- App: ${appName}
- Platform: ${platform}
- Feature/Flow: ${featureFlow}
- Severity (reported): ${sevLabel}
- Affected users (reported): ${c.review_count}
- Data source: App store reviews (clustered by semantic similarity)

Evidence — User Reports:
${evidenceLines}

---

REQUIRED OUTPUT

### 1. Root Cause Hypothesis

- likelihood: {high | medium | low}
- scope: {functional | performance | UX | monetization | stability | unknown}
- explanation: {2–4 sentences referencing review IDs e.g. [1], [2]. State what is broken and the most plausible reason, grounded only in evidence.}
- severity_assessment:
  - input: ${sevLabel}
  - suggested: {CRITICAL | HIGH | MEDIUM | LOW}
  - reason: {1–2 sentences. Required even if you agree with the input label.}

---

### 2. Affected Surface Area

- client_ui: {description or "Unknown – need more data"}
- client_logic (view models / controllers / state): {description or "Unknown – need more data"}
- network_api (endpoints, request/response handling): {description or "Unknown – need more data"}
- backend_service (API / microservice / DB behavior): {description or "Unknown – need more data"}
- config_experiments (feature flags, A/B, remote config): {description or "Unknown – need more data"}

---

### 3. Reproduction Steps

{Numbered steps an engineer or QA can follow. If evidence is too vague for precise steps, write a minimal plausible scenario and explicitly mark every assumption.}

1. …
2. …
3. …

---

### 4. Diagnostic Checklist

- client_logs: {what to search for or "Unknown – need more data"}
- backend_logs: {what to search for or "Unknown – need more data"}
- metrics: {counters, rates, or latency signals to check or "Unknown – need more data"}
- flags_experiments: {feature flags or A/B variants to verify or "Unknown – need more data"}
- other_tools (crash analytics, tracing, etc.): {tools and signals or "Unknown – need more data"}

---

### 5. Recommended Fix

- summary: {1–2 sentences. Most likely effective fix given evidence and uncertainty.}
- implementation_notes:
  - {Concrete note 1 — prefer patterns over vague requirements, e.g. "add explicit error state for playlist fetch failure" not "fix the playlist bug".}
  - {Concrete note 2, or "Unknown – need more data" if insufficient evidence.}

---

### 6. Prevention

- tests: {specific unit / integration / E2E tests to add, or "Unknown – need more data"}
- monitoring_process: {alerts, dashboards, or release checks that would have caught this earlier, or "Unknown – need more data"}

---

### 7. Notes

- uncertainties:
  - {List what you are uncertain about given the limited evidence.}
- additional_data_needed:
  - {Specific logs, signals, or context that would materially improve this analysis.}`;
}

// ============================================================ main page ===

export default function AIDebugCenterPage() {
  const searchParams = useSearchParams();
  const uploadId = searchParams?.get("upload_id") ?? null;

  const [viewMode, setViewMode] = useState<"explanation" | "prompt">(
    "explanation"
  );
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [loading, setLoading] = useState(true);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [appName, setAppName] = useState<string>("unknown");

  useEffect(() => {
    fetchClusters();
  }, [uploadId]);

  const fetchClusters = async () => {
    try {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session) return;
      const uid = session.user.id;

      if (uploadId) {
        const { data } = await supabase
          .from("clusters")
          .select("*")
          .eq("upload_id", uploadId)
          .order("severity");
        if (data) setClusters(data);

        // Fetch upload filename for prompt context
        const { data: uploadRow } = await supabase
          .from("uploads")
          .select("filename")
          .eq("id", uploadId)
          .single();
        if (uploadRow?.filename) {
          setAppName(uploadRow.filename.replace(/\.csv$/i, ""));
        }
      } else {
        const { data: uploads } = await supabase
          .from("uploads")
          .select("id")
          .eq("user_id", uid);
        if (uploads?.length) {
          const { data } = await supabase
            .from("clusters")
            .select("*")
            .in(
              "upload_id",
              uploads.map((u) => u.id)
            )
            .order("created_at", { ascending: false })
            .limit(100);
          if (data) setClusters(data);
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const copyPrompt = useCallback(
    async (c: Cluster) => {
      await navigator.clipboard.writeText(buildRCAPrompt(c, appName));
      setCopiedId(c.id);
      setTimeout(() => setCopiedId(null), 2000);
    },
    [appName]
  );

  const grouped: Record<SeverityKey, Cluster[]> = {
    critical: clusters.filter((c) => c.severity === "critical"),
    high: clusters.filter((c) => c.severity === "high"),
    medium: clusters.filter((c) => c.severity === "medium"),
    low: clusters.filter((c) => c.severity === "low"),
  };

  if (loading)
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <div className="animate-spin w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full mx-auto mb-4" />
          <p className="text-neutral-400">Loading AI Debug Center...</p>
        </div>
      </div>
    );

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between gap-4 flex-wrap"
      >
        <div>
          <h1 className="text-4xl font-black text-white mb-2 flex items-center gap-3">
            <Sparkles className="w-8 h-8 text-orange-500" />
            AI Debug Center
          </h1>
          <p className="text-neutral-400 text-sm">
            {uploadId
              ? "Category explanations pre-generated in background — ready before you finish the analytics page"
              : "All detected issues across uploads — open a specific upload for AI explanations"}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Mode toggle */}
          <div className="flex items-center gap-1 p-1 rounded-xl bg-black/40 border border-white/10">
            {(["explanation", "prompt"] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
                  viewMode === mode
                    ? "bg-gradient-to-r from-orange-500 to-red-600 text-white shadow-lg shadow-orange-500/25"
                    : "text-neutral-500 hover:text-white"
                }`}
              >
                {mode === "explanation" ? (
                  <Brain className="w-4 h-4" />
                ) : (
                  <Code2 className="w-4 h-4" />
                )}
                {mode === "explanation" ? "Explanations" : "Prompts"}
              </button>
            ))}
          </div>
        </div>
      </motion.div>

      {/* No upload_id notice */}
      {!uploadId && viewMode === "explanation" && (
        <div className="rounded-xl bg-orange-500/5 border border-orange-500/15 px-5 py-4 text-sm text-orange-400">
          💡 AI Explanations are pre-generated per upload. Navigate from{" "}
          <strong>Uploads</strong> or <strong>Analytics</strong> with an upload
          selected to see instant category insights.
        </div>
      )}

      {/* One section per severity */}
      {SEVERITIES.map((sev, i) => {
        const list = grouped[sev];
        if (!list.length) return null;
        return (
          <SeveritySection
            key={sev}
            severity={sev}
            clusters={list}
            viewMode={viewMode}
            uploadId={uploadId}
            copiedId={copiedId}
            copyPrompt={copyPrompt}
            appName={appName}
            delay={i * 0.08}
          />
        );
      })}
    </div>
  );
}

// =========================================================== section ===

function SeveritySection({
  severity,
  clusters,
  viewMode,
  uploadId,
  copiedId,
  copyPrompt,
  appName,
  delay,
}: {
  severity: SeverityKey;
  clusters: Cluster[];
  viewMode: "explanation" | "prompt";
  uploadId: string | null;
  copiedId: number | null;
  copyPrompt: (c: Cluster) => void;
  appName: string;
  delay: number;
}) {
  const s = SEV[severity];
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [explanation, setExplanation] = useState<CategoryExplanation>({
    status: "not_started",
  });
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll explanation when in explanation mode + have uploadId
  useEffect(() => {
    if (!uploadId || viewMode !== "explanation") {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }

    const poll = async () => {
      try {
        const {
          data: { session },
        } = await supabase.auth.getSession();
        const res = await fetch(
          `${BACKEND}/uploads/${uploadId}/severity-explanations/${severity}`,
          {
            headers: {
              Authorization: `Bearer ${session?.access_token ?? ""}`,
            },
          }
        );
        if (!res.ok) return;
        const data = await res.json();
        setExplanation({ status: data.status, explanation: data.explanation });
        // Stop polling once terminal state
        if (data.status === "done" || data.status === "failed") {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
        }
      } catch {}
    };

    poll(); // immediate first fetch
    pollRef.current = setInterval(poll, 5000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [uploadId, viewMode, severity]);

  const icons: Record<SeverityKey, React.ReactNode> = {
    critical: <AlertTriangle className="w-5 h-5 text-red-400" />,
    high: <AlertCircleIcon className="w-5 h-5 text-orange-400" />,
    medium: <AlertCircleIcon className="w-5 h-5 text-yellow-400" />,
    low: <Info className="w-5 h-5 text-blue-400" />,
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
      className={`rounded-2xl ${s.bg} border ${s.border} overflow-hidden`}
    >
      {/* Section header */}
      <div className={`px-6 py-4 flex items-center gap-3 border-b ${s.border}`}>
        {icons[severity]}
        <h2 className="text-lg font-bold text-white">{SEV_TITLE[severity]}</h2>
        <span
          className={`text-xs px-3 py-0.5 rounded-full border ${s.border} ${s.color} bg-white/5`}
        >
          {clusters.length} {clusters.length === 1 ? "issue" : "issues"}
        </span>

        {/* Explanation generation status badge */}
        {uploadId && viewMode === "explanation" && (
          <span
            className={`ml-auto text-[10px] uppercase tracking-wider font-semibold ${
              explanation.status === "done"
                ? "text-green-500"
                : explanation.status === "failed"
                ? "text-red-500"
                : explanation.status === "not_started"
                ? "text-neutral-600"
                : s.color
            }`}
          >
            {explanation.status === "done"
              ? "✓ Ready"
              : explanation.status === "failed"
              ? "✗ Failed"
              : explanation.status === "not_started"
              ? "Not generated"
              : "⟳ Generating…"}
          </span>
        )}
      </div>

      {/* 2-column body: clusters list | explanation */}
      <div
        className={`grid grid-cols-5 divide-x ${s.divider}`}
        style={{ minHeight: "260px" }}
      >
        {/* LEFT (2/5) — scrollable cluster list */}
        <div
          className="col-span-2 overflow-y-auto"
          style={{ maxHeight: "520px" }}
        >
          {clusters.map((c, idx) => {
            const title = cleanTitle(c.title);
            const isSelected = selectedId === c.id;
            const reviews = c.sample_reviews || [];
            return (
              <div key={c.id} className={`border-b border-white/4 ${isSelected ? `border-l-2 ${s.border}` : "border-l-2 border-transparent"}`}>
                {/* Cluster header row */}
                <motion.div
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.03 * idx }}
                  onClick={() => setSelectedId(isSelected ? null : c.id)}
                  className={`px-4 py-3 cursor-pointer hover:bg-white/3 transition-colors flex items-start gap-3 ${
                    isSelected ? "bg-white/5 pl-3" : ""
                  }`}
                >
                  <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1.5 ${s.dot}`} />
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-semibold leading-tight ${isSelected ? "text-white" : "text-neutral-300"}`}>
                      {title}
                    </p>
                    <p className="text-xs text-neutral-500 mt-1">
                      {c.review_count.toLocaleString()} reviews
                      {reviews.length > 0 && ` · ${reviews.length} samples`}
                      {" · "}{STATUS_EMOJI[c.status] ?? "❓"}{" "}{c.status?.replace("_", " ")}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {viewMode === "prompt" && (
                      <button
                        onClick={(e) => { e.stopPropagation(); copyPrompt(c); }}
                        className={`p-1.5 rounded-lg border ${s.border} ${s.bg} ${s.color} hover:bg-white/10 transition-all`}
                        title="Copy debug prompt"
                      >
                        {copiedId === c.id ? <CheckCircle2 className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                      </button>
                    )}
                    {isSelected
                      ? <ChevronUp className={`w-3.5 h-3.5 ${s.color}`} />
                      : <ChevronDown className="w-3.5 h-3.5 text-neutral-600" />}
                  </div>
                </motion.div>

                {/* Inline reviews — shown when cluster is expanded */}
                <AnimatePresence>
                  {isSelected && reviews.length > 0 && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.22, ease: "easeInOut" }}
                      className="overflow-hidden"
                    >
                      <div className={`mx-3 mb-3 rounded-lg ${s.bg} border ${s.border} overflow-hidden`}>
                        <p className={`px-3 pt-2.5 pb-1 text-[9px] font-bold uppercase tracking-wider ${s.color}`}>
                          Sample Reviews ({reviews.length})
                        </p>
                        {reviews.slice(0, 8).map((r, ri) => (
                          <div key={ri} className="px-3 py-2 border-t border-white/4">
                            <div className="flex items-center gap-2 mb-1">
                              {r.rating != null && (
                                <div className="flex items-center gap-0.5">
                                  {Array.from({ length: 5 }).map((_, si) => (
                                    <Star key={si} className={`w-2 h-2 ${
                                      si < (r.rating ?? 0)
                                        ? "fill-yellow-500 text-yellow-500"
                                        : "text-neutral-700"
                                    }`} />
                                  ))}
                                </div>
                              )}
                              {r.device && <span className="text-[9px] text-neutral-700">{r.device}</span>}
                              {r.version && <span className="text-[9px] text-neutral-700">v{r.version}</span>}
                              <span className="text-[9px] text-neutral-800 ml-auto">#{ri + 1}</span>
                            </div>
                            <p className="text-[11px] text-neutral-400 leading-relaxed">{r.content}</p>
                          </div>
                        ))}
                        {reviews.length > 8 && (
                          <p className="px-3 py-2 text-[10px] text-neutral-700 border-t border-white/4">
                            +{reviews.length - 8} more stored
                          </p>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </div>

        {/* RIGHT (3/5) — explanation or prompt preview */}
        <div
          className="col-span-3 p-5 overflow-y-auto"
          style={{ maxHeight: "520px" }}
        >
          {viewMode === "explanation" ? (
            <ExplanationPanel
              explanation={explanation}
              s={s}
              severity={severity}
              uploadId={uploadId}
            />
          ) : (
            <PromptPanel
              clusters={clusters}
              selectedId={selectedId}
              s={s}
              copiedId={copiedId}
              copyPrompt={copyPrompt}
              appName={appName}
            />
          )}
        </div>
      </div>
    </motion.div>
  );
}

// ============================================= right panel: explanation ===

function ExplanationPanel({
  explanation,
  s,
  severity,
  uploadId,
}: {
  explanation: CategoryExplanation;
  s: (typeof SEV)["critical"];
  severity: string;
  uploadId: string | null;
}) {
  const renderText = (text: string) =>
    text.split("\n").map((line, i) => {
      const parts = line.split(/\*\*(.*?)\*\*/);
      return (
        <span key={i} className="block mb-2 leading-relaxed">
          {parts.map((part, j) =>
            j % 2 === 1 ? (
              <strong key={j} className={`font-bold ${s.color}`}>
                {part}
              </strong>
            ) : (
              <span key={j}>{part}</span>
            )
          )}
        </span>
      );
    });

  if (!uploadId) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 py-12 text-center">
        <Brain className={`w-8 h-8 ${s.color} opacity-20`} />
        <p className="text-xs text-neutral-600">
          Select a specific upload to see AI explanations
        </p>
      </div>
    );
  }

  if (explanation.status === "not_started") {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 py-12 text-center">
        <Brain className={`w-8 h-8 ${s.color} opacity-20`} />
        <p className="text-sm text-neutral-500">No explanation yet</p>
        <p className="text-xs text-neutral-700">
          Click{" "}
          <span className={`font-semibold ${s.color}`}>Pre-generate All</span>{" "}
          at the top to start
        </p>
      </div>
    );
  }

  if (
    explanation.status === "pending" ||
    explanation.status === "generating"
  ) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 py-12">
        <Loader2 className={`w-6 h-6 animate-spin ${s.color}`} />
        <div className="text-center">
          <p className={`text-sm font-semibold ${s.color}`}>
            Generating {severity} explanation…
          </p>
          <p className="text-xs text-neutral-600 mt-1">
            Analysing all {severity} clusters in the background
          </p>
        </div>
        <div className="flex gap-1 mt-1">
          {[0, 1, 2].map((i) => (
            <motion.div
              key={i}
              animate={{ scale: [1, 1.4, 1], opacity: [0.3, 1, 0.3] }}
              transition={{ repeat: Infinity, duration: 1.4, delay: i * 0.22 }}
              className={`w-1.5 h-1.5 rounded-full ${s.dot}`}
            />
          ))}
        </div>
      </div>
    );
  }

  if (explanation.status === "failed") {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 py-12 text-center">
        <p className="text-sm text-red-400">Generation failed</p>
        <p className="text-xs text-neutral-600">
          Click Pre-generate All to retry
        </p>
      </div>
    );
  }

  // done
  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <Brain className={`w-3.5 h-3.5 ${s.color}`} />
        <p
          className={`text-[10px] font-bold uppercase tracking-wider ${s.color}`}
        >
          AI Category Analysis
        </p>
      </div>
      <div className="text-sm text-neutral-300">
        {renderText(explanation.explanation ?? "")}
      </div>
    </div>
  );
}

// ================================================= right panel: prompts ===

function PromptPanel({
  clusters,
  selectedId,
  s,
  copiedId,
  copyPrompt,
  appName,
}: {
  clusters: Cluster[];
  selectedId: number | null;
  s: (typeof SEV)["critical"];
  copiedId: number | null;
  copyPrompt: (c: Cluster) => void;
  appName: string;
}) {
  const selected = selectedId ? clusters.find((c) => c.id === selectedId) : null;

  if (!selected) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 py-12 text-center">
        <Code2 className={`w-7 h-7 ${s.color} opacity-20`} />
        <p className="text-sm text-neutral-600">
          Select a cluster on the left to preview its debug prompt
        </p>
      </div>
    );
  }

  const title = cleanTitle(selected.title);
  const promptText = buildRCAPrompt(selected, appName);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Code2 className={`w-3.5 h-3.5 ${s.color}`} />
          <p
            className={`text-[10px] font-bold uppercase tracking-wider ${s.color}`}
          >
            Debug Prompt
          </p>
          <span className="text-[10px] text-neutral-600 ml-2 truncate max-w-[180px]">
            — {title}
          </span>
        </div>
        <button
          onClick={() => copyPrompt(selected)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium ${s.bg} border ${s.border} ${s.color} hover:bg-white/10 transition-all`}
        >
          {copiedId === selected.id ? (
            <>
              <CheckCircle2 className="w-3 h-3" /> Copied!
            </>
          ) : (
            <>
              <Copy className="w-3 h-3" /> Copy
            </>
          )}
        </button>
      </div>
      <pre
        className={`text-xs font-mono text-neutral-300 leading-relaxed whitespace-pre-wrap break-words rounded-lg p-4 ${s.bg} border ${s.border}`}
      >
        {promptText}
      </pre>

      {/* Nearby clusters */}
      <p className="text-[10px] text-neutral-700 mt-4 mb-2 uppercase tracking-wider">
        Other clusters in this category
      </p>
      <div className="space-y-1">
        {clusters
          .filter((c) => c.id !== selected.id)
          .slice(0, 5)
          .map((c) => (
            <div
              key={c.id}
              className="text-[11px] text-neutral-500 flex items-center gap-2"
            >
              <div
                className={`w-1 h-1 rounded-full flex-shrink-0 ${s.dot} opacity-50`}
              />
              <span className="truncate">{cleanTitle(c.title)}</span>
              <span className="text-neutral-700 flex-shrink-0">
                {c.review_count.toLocaleString()}
              </span>
            </div>
          ))}
      </div>
    </div>
  );
}
