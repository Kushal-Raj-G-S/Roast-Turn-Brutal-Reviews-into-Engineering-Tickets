"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useState, useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import {
  Sparkles,
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
  FlaskConical,
  Play,
  RotateCcw,
} from "lucide-react";
import { supabase } from "@/lib/supabase/client";
import { apiClient } from "@/lib/api-client";
import type { AgentMetadata } from "@/lib/api-client";

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
  ai_metadata?: AgentMetadata | null;
  rca_hypothesis?: string | null;
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

  const [viewMode, setViewMode] = useState<"explanation" | "playground">(
    "explanation"
  );
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [loading, setLoading] = useState(true);
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
            {(["explanation", "playground"] as const).map((mode) => (
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
                  <FlaskConical className="w-4 h-4" />
                )}
                {mode === "explanation" ? "Explanations" : "Playground"}
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

      {!uploadId && viewMode === "playground" && (
        <div className="rounded-xl bg-purple-500/5 border border-purple-500/15 px-5 py-4 text-sm text-purple-300">
          🧪 The playground runs against a specific cluster&apos;s data. Open a
          specific upload to pick one and start experimenting.
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
  appName,
  delay,
}: {
  severity: SeverityKey;
  clusters: Cluster[];
  viewMode: "explanation" | "playground";
  uploadId: string | null;
  appName: string;
  delay: number;
}) {
  const s = SEV[severity];
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [explanation, setExplanation] = useState<CategoryExplanation>({
    status: "not_started",
  });
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Lets a clicked citation in the explanation text scroll its real cluster
  // into view on the left, not just expand it off-screen.
  const clusterRefs = useRef<Record<number, HTMLDivElement | null>>({});

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
              <div
                key={c.id}
                ref={(el) => { clusterRefs.current[c.id] = el; }}
                className={`border-b border-white/4 ${isSelected ? `border-l-2 ${s.border}` : "border-l-2 border-transparent"}`}
              >
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
              allClusters={clusters}
              onCite={(clusterId) => {
                setSelectedId(clusterId);
                clusterRefs.current[clusterId]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
              }}
            />
          ) : (
            <PlaygroundPanel
              clusters={clusters}
              selectedId={selectedId}
              s={s}
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
  allClusters,
  onCite,
}: {
  explanation: CategoryExplanation;
  s: (typeof SEV)[keyof typeof SEV];
  severity: string;
  uploadId: string | null;
  allClusters: Cluster[];
  onCite: (clusterId: number) => void;
}) {
  const escapeRegExp = (str: string) => str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  // Turns each cluster's title into a clickable citation wherever it's
  // literally mentioned in the explanation prose (the generation prompt
  // feeds the model these exact titles and asks it to reference them, so
  // they reliably show up verbatim). Clicking one jumps to the real
  // cluster + its actual sample reviews on the left, instead of asking you
  // to just trust the AI's summary of them.
  const renderText = (text: string) => {
    const titleEntries = allClusters
      .map((c) => ({ id: c.id, title: cleanTitle(c.title).trim() }))
      .filter((t) => t.title.length >= 6)
      .sort((a, b) => b.title.length - a.title.length);
    const titleToId = new Map(titleEntries.map((t) => [t.title.toLowerCase(), t.id]));
    const citationPattern =
      titleEntries.length > 0
        ? new RegExp(`(${titleEntries.map((t) => escapeRegExp(t.title)).join("|")})`, "gi")
        : null;

    return text.split("\n").map((line, i) => {
      const boldParts = line.split(/\*\*(.*?)\*\*/);
      return (
        <span key={i} className="block mb-2 leading-relaxed">
          {boldParts.map((part, j) => {
            const content = citationPattern
              ? part.split(citationPattern).map((seg, k) => {
                  const clusterId = titleToId.get(seg.toLowerCase());
                  if (clusterId !== undefined) {
                    return (
                      <button
                        key={k}
                        type="button"
                        onClick={() => onCite(clusterId)}
                        className={`underline decoration-dotted underline-offset-2 ${s.color} hover:text-white font-semibold cursor-pointer`}
                        title="Click to see the real reviews behind this"
                      >
                        {seg}
                      </button>
                    );
                  }
                  return <span key={k}>{seg}</span>;
                })
              : part;
            return j % 2 === 1 ? (
              <strong key={j} className={`font-bold ${s.color}`}>
                {content}
              </strong>
            ) : (
              <span key={j}>{content}</span>
            );
          })}
        </span>
      );
    });
  };

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

// ============================================= right panel: agent trace ===

// This is a STYLE PICKER, not a real model switch. Actually routing each
// pick to NVIDIA as a real `model=` id was tried and reverted: NVIDIA's
// public catalog lists ~100 models, but this account can only actually
// invoke a couple of them — 16 of 19 "popular" ids tested here came back
// 404/410/"Function not found for account", including ones the catalog
// listing itself claimed were available. Instead, every pick below always
// runs through the one configured, verified-fast model, and is passed to
// the backend purely as a persona label that flavors the system prompt --
// see playground_run()'s docstring in bulk_routes.py. That's why it's safe
// to list many recognizable names here again without re-verifying each one.
const POPULAR_MODELS = [
  // Meta
  { id: "meta/llama-3.1-8b-instruct", label: "Llama 3.1 8B", note: "the real default model", family: "Meta" },
  { id: "meta/llama-3.1-70b-instruct", label: "Llama 3.1 70B", note: "stronger reasoning", family: "Meta" },
  { id: "meta/llama-3.3-70b-instruct", label: "Llama 3.3 70B", note: "newest Meta", family: "Meta" },
  // OpenAI (open-weight)
  { id: "openai/gpt-oss-120b", label: "GPT-OSS 120B", note: "OpenAI open-weight", family: "OpenAI" },
  { id: "openai/gpt-oss-20b", label: "GPT-OSS 20B", note: "OpenAI open-weight · compact", family: "OpenAI" },
  // DeepSeek
  { id: "deepseek-ai/deepseek-r1", label: "DeepSeek R1", note: "reasoning specialist", family: "DeepSeek" },
  { id: "deepseek-ai/deepseek-v4-flash-0731", label: "DeepSeek V4 Flash", note: "fast", family: "DeepSeek" },
  // Qwen (Alibaba)
  { id: "qwen/qwen2.5-72b-instruct", label: "Qwen 2.5 72B", note: "large · strong", family: "Qwen" },
  { id: "qwen/qwq-32b-preview", label: "QwQ 32B", note: "reasoning-focused", family: "Qwen" },
  // GLM (Zhipu AI)
  { id: "zhipuai/glm-4-9b-chat", label: "GLM-4 9B", note: "Zhipu AI", family: "GLM" },
  // Moonshot AI
  { id: "moonshotai/kimi-k3", label: "Kimi K3", note: "Moonshot AI", family: "Moonshot" },
  // Mistral
  { id: "mistralai/mistral-large-2-instruct", label: "Mistral Large 2", note: "flagship", family: "Mistral" },
  { id: "mistralai/mixtral-8x22b-v0.1", label: "Mixtral 8x22B", note: "mixture-of-experts", family: "Mistral" },
  // Google
  { id: "google/gemma-3-12b-it", label: "Gemma 3 12B", note: "Google", family: "Google" },
  // Microsoft
  { id: "microsoft/phi-3.5-moe-instruct", label: "Phi-3.5 MoE", note: "Microsoft", family: "Microsoft" },
  // NVIDIA-tuned
  { id: "nvidia/llama-3.1-nemotron-ultra-253b-v1", label: "Nemotron Ultra 253B", note: "NVIDIA · huge reasoning", family: "NVIDIA" },
];

function PlaygroundPanel({
  clusters,
  selectedId,
  s,
  appName,
}: {
  clusters: Cluster[];
  selectedId: number | null;
  s: (typeof SEV)[keyof typeof SEV];
  appName: string;
}) {
  const selected = selectedId ? clusters.find((c) => c.id === selectedId) : null;
  // One box holds either the default prompt or the last generated result —
  // running replaces its content in place rather than showing a second
  // panel, so it's always obvious what you're looking at right now.
  const [box, setBox] = useState("");
  const [isResult, setIsResult] = useState(false);
  const [model, setModel] = useState("");
  const [modelOpen, setModelOpen] = useState(false);
  const [temperature, setTemperature] = useState(0.2);
  const [modelUsed, setModelUsed] = useState<string | null>(null);
  const [personaUsed, setPersonaUsed] = useState<string | null>(null);
  const [tempUsed, setTempUsed] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (selected) {
      setBox(buildRCAPrompt(selected, appName));
      setIsResult(false);
      setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.id]);

  const copyBox = async () => {
    await navigator.clipboard.writeText(box);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const resetPrompt = () => {
    if (!selected) return;
    setBox(buildRCAPrompt(selected, appName));
    setIsResult(false);
    setError(null);
  };

  const run = async () => {
    if (!selected || !box.trim()) return;
    setLoading(true);
    setError(null);
    const promptSent = box;
    try {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (session) apiClient.setToken(session.access_token);
      const result = await apiClient.runPlayground(selected.id, {
        prompt: promptSent,
        model: model.trim() || undefined,
        temperature,
      });
      setBox(result.output);
      setIsResult(true);
      setModelUsed(result.model_used);
      setPersonaUsed(result.persona_used);
      setTempUsed(result.temperature_used);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Run failed");
    } finally {
      setLoading(false);
    }
  };

  if (!selected) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 py-12 text-center">
        <FlaskConical className={`w-7 h-7 ${s.color} opacity-20`} />
        <p className="text-sm text-neutral-600">
          Select a cluster on the left, tweak the model/temperature, and run it
          live — nothing here gets saved to the cluster
        </p>
      </div>
    );
  }

  const title = cleanTitle(selected.title);

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <FlaskConical className={`w-3.5 h-3.5 ${s.color}`} />
          <p className={`text-[10px] font-bold uppercase tracking-wider ${s.color}`}>
            Live Playground
          </p>
          <span className="text-[10px] text-neutral-600 ml-2 truncate max-w-[180px]">
            — {title}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={copyBox}
            className="flex items-center gap-1 text-[10px] text-neutral-500 hover:text-white transition-colors"
          >
            {copied ? (
              <>
                <CheckCircle2 className="w-3 h-3" /> Copied!
              </>
            ) : (
              <>
                <Copy className="w-3 h-3" /> Copy
              </>
            )}
          </button>
          <button
            onClick={resetPrompt}
            className="flex items-center gap-1 text-[10px] text-neutral-500 hover:text-white transition-colors"
          >
            <RotateCcw className="w-3 h-3" /> Reset prompt
          </button>
        </div>
      </div>

      {/* Model / temperature / run — above the box, since these are the
          controls you set BEFORE deciding to replace what's in it. "Model"
          here is a style persona, not a real model swap — see the note
          above POPULAR_MODELS for why. Temperature is applied for real. */}
      <div className="flex flex-wrap items-center gap-3 mb-1">
        <div className="relative flex items-center gap-2">
          <label className="text-[10px] uppercase tracking-wide text-neutral-500">
            Model style
          </label>
          <div className="relative w-72">
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              onFocus={() => setModelOpen(true)}
              onBlur={() => setModelOpen(false)}
              placeholder="default (meta/llama-3.1-8b-instruct)"
              className={`w-full text-xs bg-black/30 border rounded-lg pl-2 pr-7 py-1.5 text-neutral-300 focus:outline-none transition-colors ${
                modelOpen ? "border-purple-500/50" : "border-white/10"
              }`}
            />
            <ChevronDown
              className={`absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-neutral-500 pointer-events-none transition-transform ${
                modelOpen ? "rotate-180" : ""
              }`}
            />
            {modelOpen && (() => {
              const filtered = POPULAR_MODELS.filter(
                (m) =>
                  !model.trim() ||
                  m.id.toLowerCase().includes(model.toLowerCase()) ||
                  m.label.toLowerCase().includes(model.toLowerCase()) ||
                  m.family.toLowerCase().includes(model.toLowerCase())
              );
              const families = Array.from(new Set(filtered.map((m) => m.family)));

              return (
                <div className="absolute z-20 top-full left-0 mt-1.5 w-full max-h-72 overflow-y-auto rounded-lg border border-white/10 bg-neutral-900 shadow-2xl shadow-black/50">
                  {families.length === 0 && (
                    <p className="px-3 py-3 text-xs text-neutral-600">
                      No matches — Run will still use whatever you&apos;ve typed as a custom model
                    </p>
                  )}
                  {families.map((family) => (
                    <div key={family}>
                      <p className="px-3 pt-2 pb-1 text-[9px] font-bold uppercase tracking-wider text-purple-400/70 bg-white/[0.03]">
                        {family}
                      </p>
                      {filtered
                        .filter((m) => m.family === family)
                        .map((m) => (
                          <button
                            key={m.id}
                            type="button"
                            onMouseDown={(e) => e.preventDefault()}
                            onClick={() => {
                              setModel(m.id);
                              setModelOpen(false);
                            }}
                            className={`w-full text-left px-3 py-2 flex items-center justify-between gap-3 transition-colors hover:bg-purple-500/10 ${
                              model === m.id ? "bg-purple-500/15" : ""
                            }`}
                          >
                            <span className="min-w-0">
                              <span className="block text-xs font-semibold text-neutral-200 truncate">
                                {m.label}
                              </span>
                              <span className="block text-[10px] font-mono text-neutral-500 truncate">
                                {m.id}
                              </span>
                            </span>
                            <span className="text-[9px] text-neutral-600 whitespace-nowrap flex-shrink-0">
                              {m.note}
                            </span>
                          </button>
                        ))}
                    </div>
                  ))}
                  {model.trim() &&
                    !POPULAR_MODELS.some((m) => m.id === model.trim()) && (
                      <p className="px-3 py-2 text-[10px] text-neutral-600 border-t border-white/5">
                        Using custom model:{" "}
                        <span className="font-mono text-neutral-400">{model.trim()}</span>
                      </p>
                    )}
                </div>
              );
            })()}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-[10px] uppercase tracking-wide text-neutral-500">
            Temp
          </label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.1}
            value={temperature}
            onChange={(e) => setTemperature(parseFloat(e.target.value))}
            className="w-24"
          />
          <span className="text-xs text-neutral-400 font-mono w-8">
            {temperature.toFixed(1)}
          </span>
        </div>
        <button
          onClick={run}
          disabled={loading || !box.trim()}
          className={`ml-auto flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold ${s.bg} border ${s.border} ${s.color} hover:bg-white/10 transition-all disabled:opacity-40 disabled:cursor-not-allowed`}
        >
          {loading ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <Play className="w-3 h-3" />
          )}
          {loading ? "Running…" : "Run"}
        </button>
      </div>

      {error && <p className="text-xs text-red-400 mb-3">{error}</p>}

      {/* The default prompt lives here until you run — then this same box
          shows the result instead. The overlay is the only way you'd know
          a new one is being generated, since nothing else on screen moves. */}
      <div className="relative">
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center gap-2 rounded-lg bg-black/75 backdrop-blur-[1px]">
            <Loader2 className="w-4 h-4 animate-spin text-white" />
            <span className="text-xs text-neutral-200">
              Generating with {model.trim() || "default"} (temp {temperature.toFixed(1)})…
            </span>
          </div>
        )}
        <p
          className={`text-[10px] uppercase tracking-wide mb-1.5 ${
            isResult ? "text-emerald-500" : "text-neutral-500"
          }`}
        >
          {isResult
            ? `Result — ${personaUsed || modelUsed}, temp ${tempUsed?.toFixed(1)}`
            : "Default prompt (editable)"}
        </p>
        <textarea
          value={box}
          onChange={(e) => setBox(e.target.value)}
          rows={12}
          className={`w-full text-xs font-mono leading-relaxed rounded-lg p-3 focus:outline-none focus:border-white/30 resize-y ${
            isResult
              ? "text-neutral-200 bg-emerald-500/5 border border-emerald-500/25"
              : `text-neutral-300 ${s.bg} border ${s.border}`
          }`}
          placeholder="Edit the prompt..."
        />
      </div>

      {selected.rca_hypothesis?.trim() && (
        <p className="text-[10px] text-neutral-600 mt-2 truncate">
          Stored hypothesis on file:{" "}
          <span className="text-neutral-500">{selected.rca_hypothesis.trim()}</span>
        </p>
      )}
    </div>
  );
}
