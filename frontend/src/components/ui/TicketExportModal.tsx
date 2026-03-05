"use client";

/**
 * TicketExportModal
 * =================
 * Export a cluster as a tracking ticket to GitHub Issues, Linear, or Markdown.
 * All API keys are used only in the browser request — never sent to our backend.
 */

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Copy,
  Check,
  ExternalLink,
  Loader2,
  Ticket,
  Github,
  AlertCircle,
} from "lucide-react";

// ─────────────────────────────────── types ────────────────────────────────────

interface SampleReview {
  content: string;
  rating?: number;
  version?: string;
  device?: string;
}

export interface ExportableCluster {
  id: number;
  title: string;
  severity: string;
  status: string;
  review_count: number;
  sample_reviews?: SampleReview[];
  affected_versions?: string[];
  affected_devices?: string[];
  keywords?: string[];
  rca_hypothesis?: string;
  regression_detected?: boolean;
  regression_of_title?: string;
}

interface Props {
  cluster: ExportableCluster;
  appName?: string;
  onClose: () => void;
}

type Tab = "github" | "linear" | "copy";

// ─────────────────────────────── helpers ──────────────────────────────────────

const SEV_EMOJI: Record<string, string> = {
  critical: "🚨",
  high: "🔴",
  medium: "🟡",
  low: "🔵",
};

function cleanTitle(t: string) {
  return t
    .replace(/^\[(CRITICAL|HIGH|MEDIUM|LOW)\]\s*(Issue:\s*)?/i, "")
    .replace(/^Issue:\s*/i, "")
    .trim();
}

// ── Semantic cluster type detection ──────────────────────────────────────────

type ClusterType =
  | "positive"
  | "feature_request"
  | "complaint"
  | "crash"
  | "ad"
  | "login"
  | "payment"
  | "performance"
  | "gameplay"
  | "ui"
  | "bug";

function detectClusterType(title: string, keywords: string[]): ClusterType {
  const haystack = (title + " " + keywords.join(" ")).toLowerCase();

  // Positive / praise — check first, highest priority
  if (
    /\b(fun|enjoy|love|great|amazing|awesome|best|addictive|fantastic|wonderful|excellent|perfect|happy|like playing|keep playing|highly recommend|good game|good app|nice|brilliant|superb|entertaining|pleasant|satisfying|smooth)\b/.test(
      haystack
    )
  )
    return "positive";

  // Feature request
  if (
    /\bplease add|would be nice|wish|could you add|want a feature|feature request|suggestion|add option|add a|would love|needs a|should have|missing option|allow us\b/.test(
      haystack
    )
  )
    return "feature_request";

  // Technical bug subtypes (checked before generic complaint)
  if (/\bcrash|crashing|force close|not open|freeze|stuck|black screen|keeps closing|app dies\b/.test(haystack))
    return "crash";
  if (/\bad\b|ads|advertisement|rewarded video|ad sdk|ad fail|ad not|watching ad/.test(haystack))
    return "ad";
  if (/\blogin|sign in|sign out|account|password|otp|verify|logout|session expired|cant log\b/.test(haystack))
    return "login";
  if (/\bpay|paid|purchase|subscription|refund|charge|money|buy|billing|in-app purchase\b/.test(haystack))
    return "payment";
  if (/\blag|slow|loading|battery|hang|performance|takes long|drains|fps|stutter|unresponsive\b/.test(haystack))
    return "performance";
  if (/\bui|design|button|screen|dark mode|interface|layout|display|visual|broken ui|render|overlapping\b/.test(haystack))
    return "ui";
  if (/\blevel|lives|score|feature|gameplay|missing feature|removed|update broke|progression|game mode\b/.test(haystack))
    return "gameplay";

  // Complaint — negative sentiment but no specific technical failure
  if (
    /\bannoy|disappointing|hate|terrible|worst|bad|too many|unfair|pay to win|expensive|greedy|boring|waste of time|garbage|useless|ridiculous|scam\b/.test(
      haystack
    )
  )
    return "complaint";

  return "bug";
}

// ── Signal strength from review volume ───────────────────────────────────────

function signalStrength(count: number): { label: string; confidence: string; volumeDesc: string } {
  if (count >= 500)  return { label: "Dominant",    confidence: "0.97", volumeDesc: `Dominant sentiment — ${count} users independently reported this` };
  if (count >= 100)  return { label: "Very Strong",  confidence: "0.91", volumeDesc: `Very strong signal detected across ${count} user reviews` };
  if (count >= 20)   return { label: "Strong",       confidence: "0.82", volumeDesc: `Strong signal detected from ${count} clustered user reviews` };
  if (count >= 5)    return { label: "Moderate",     confidence: "0.70", volumeDesc: `Moderate signal from ${count} user reviews` };
  return               { label: "Weak",          confidence: "0.55", volumeDesc: `Early signal detected from ${count} user review${count !== 1 ? "s" : ""}` };
}

// ── Theme label from type ─────────────────────────────────────────────────────

const THEME_LABEL: Record<ClusterType, string> = {
  positive:        "Positive Sentiment / User Enjoyment",
  feature_request: "Feature Request / User Suggestion",
  complaint:       "User Dissatisfaction / Sentiment Issue",
  crash:           "Crashes & Stability",
  ad:              "Advertisement / Ad SDK Failure",
  login:           "Login & Account Access",
  payment:         "In-App Purchases & Billing",
  performance:     "Performance & Responsiveness",
  gameplay:        "Gameplay / Feature Regression",
  ui:              "UI & Visual Rendering",
  bug:             "Application Bug / Malfunction",
};

const TYPE_EMOJI: Record<ClusterType, string> = {
  positive:        "💚",
  feature_request: "💡",
  complaint:       "🟡",
  crash:           "🔴",
  ad:              "📢",
  login:           "🔑",
  payment:         "💸",
  performance:     "🐢",
  gameplay:        "🎮",
  ui:              "🎨",
  bug:             "🐛",
};

// ── Main markdown builder ─────────────────────────────────────────────────────

function buildMarkdown(cluster: ExportableCluster, appName?: string): string {
  const sev = cluster.severity.toUpperCase();
  const title = cleanTitle(cluster.title);
  const clusterType = detectClusterType(title, cluster.keywords ?? []);
  const sig = signalStrength(cluster.review_count);
  const typeEmoji = TYPE_EMOJI[clusterType];
  const theme = THEME_LABEL[clusterType];
  const statusLabel: Record<string, string> = {
    fresh_roast: "Fresh Roast",
    assigned: "Assigned",
    in_progress: "In Progress",
    resolved: "Resolved",
    wont_fix: "Won't Fix",
  };

  const lines: string[] = [];

  // ── Shared evidence block ──
  const reviews = cluster.sample_reviews?.slice(0, 8) ?? [];
  const evidenceBlock = () => {
    if (reviews.length === 0) return;
    lines.push(`---\n`);
    lines.push(`### User Voices\n`);
    reviews.forEach((r) => {
      const starCount = r.rating ?? 0;
      const stars = starCount > 0 ? `${starCount} ${"⭐".repeat(Math.min(starCount, 5))}` : "";
      const meta = [r.version ? `v${r.version}` : "", r.device].filter(Boolean).join(" · ");
      const header = [stars, meta].filter(Boolean).join("  ·  ");
      if (header) lines.push(header + "  ");
      lines.push(`> "${r.content.trim()}"\n`);
    });
  };

  // ── Shared meta block ──
  const metaBlock = () => {
    lines.push(`**Theme:** ${theme}  `);
    lines.push(`**Source:** ${appName ? `${appName} — ` : ""}App Review Clustering (Roast)  `);
    lines.push(`**Cluster ID:** ${cluster.id}  `);
    lines.push(`**Severity:** ${sev}  `);
    lines.push(`**Reports:** ${cluster.review_count}  `);
    lines.push(`**Signal Strength:** ${sig.label} | **Confidence:** ${sig.confidence}  `);
    lines.push(`**Status:** ${statusLabel[cluster.status] ?? cluster.status}  `);
    if (cluster.affected_versions?.length)
      lines.push(`**Affected Versions:** ${cluster.affected_versions.slice(0, 6).join(", ")}  `);
    if (cluster.affected_devices?.length)
      lines.push(`**Affected Devices:** ${cluster.affected_devices.slice(0, 4).join(", ")}  `);
    if (cluster.regression_detected && cluster.regression_of_title)
      lines.push(`**⚠️ Regression of:** ${cluster.regression_of_title}  `);
    lines.push("");
  };

  // ═══════════════════════════════════════════════════════════════════════════
  //  POSITIVE CLUSTER — praise / enjoyment / satisfaction
  // ═══════════════════════════════════════════════════════════════════════════
  if (clusterType === "positive") {
    lines.push(`## 💚 Positive Feedback Cluster\n`);
    metaBlock();
    lines.push(`---\n`);
    lines.push(`### Summary\n`);
    lines.push(
      cluster.rca_hypothesis ??
      `Users consistently express **high enjoyment and satisfaction**, making this one of the strongest positive signals in the current batch.\n\nThis is not a bug — this is a product insight.`
    );
    lines.push("");
    evidenceBlock();
    lines.push(`---\n`);
    lines.push(`### Product Signals\n`);
    lines.push(`• ${sig.volumeDesc}  `);
    lines.push(`• Strong engagement driver — consider featuring in App Store listing or marketing  `);
    lines.push(`• Use as a baseline sentiment benchmark for future releases  `);
    if (cluster.review_count >= 100)
      lines.push(`• Dominant cluster — may be offsetting critical/high severity clusters in store rating  `);
    lines.push("");
    lines.push(`---\n`);
    lines.push(`### Recommended Actions\n`);
    lines.push(`• **Route to:** Product / Marketing — not Engineering  `);
    lines.push(`• Consider featuring select reviews in promotional materials or app store screenshots  `);
    lines.push(`• Surface to the growth team as a retention signal  `);
    lines.push("");
    lines.push(`---\n`);
    lines.push(`### Labels\n`);
    lines.push(`\`positive-feedback\` \`${cluster.severity}\` \`user-reported\` \`app-reviews\` \`ai-detected\``);
    return lines.join("\n");
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  FEATURE REQUEST — suggestion / want / wish
  // ═══════════════════════════════════════════════════════════════════════════
  if (clusterType === "feature_request") {
    lines.push(`## 💡 Feature Request Cluster\n`);
    metaBlock();
    lines.push(`---\n`);
    lines.push(`### Summary\n`);
    lines.push(
      cluster.rca_hypothesis ??
      `Users are requesting **${title.toLowerCase()}**.\n\nThis cluster represents an unmet user expectation or a perceived gap compared to competing apps, detected across ${cluster.review_count} independent reviews.`
    );
    lines.push("");
    evidenceBlock();
    lines.push(`---\n`);
    lines.push(`### Product Signals\n`);
    lines.push(`• ${sig.volumeDesc}  `);
    lines.push(`• Signals unmet user expectation or competitive feature gap  `);
    if (cluster.review_count >= 50)
      lines.push(`• Volume is high enough to justify adding to the product backlog  `);
    lines.push("");
    lines.push(`---\n`);
    lines.push(`### Recommended Actions\n`);
    lines.push(`• **Route to:** Product Management — not Engineering  `);
    lines.push(`• Add to feature request tracker / backlog  `);
    lines.push(`• Cross-reference with existing roadmap items  `);
    if (cluster.keywords?.length)
      lines.push(`• Keywords: ${cluster.keywords.slice(0, 6).map((k) => `\`${k}\``).join(" ")}  `);
    lines.push("");
    lines.push(`---\n`);
    lines.push(`### Labels\n`);
    lines.push(`\`feature-request\` \`${cluster.severity}\` \`user-reported\` \`app-reviews\` \`ai-detected\``);
    return lines.join("\n");
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  COMPLAINT — negative sentiment, no specific technical failure
  // ═══════════════════════════════════════════════════════════════════════════
  if (clusterType === "complaint") {
    lines.push(`## 🟡 User Sentiment Cluster — Complaint\n`);
    metaBlock();
    lines.push(`---\n`);
    lines.push(`### Summary\n`);
    lines.push(
      cluster.rca_hypothesis ??
      `Users express dissatisfaction related to **${title.toLowerCase()}**.\n\nThis cluster represents negative user sentiment without a specific technical failure — it may indicate a product design, monetisation, or game-balance concern.`
    );
    lines.push("");
    evidenceBlock();
    lines.push(`---\n`);
    lines.push(`### Impact\n`);
    lines.push(`• ${sig.volumeDesc}  `);
    lines.push(`• May be contributing to lower store rating if unaddressed  `);
    lines.push(`• Sentiment clusters at this volume surface organically in app store reviews  `);
    if (cluster.severity === "critical" || cluster.severity === "high")
      lines.push(`• Volume and severity warrant review by the product team  `);
    lines.push("");
    lines.push(`---\n`);
    lines.push(`### Recommended Actions\n`);
    lines.push(`• **Route to:** Product / UX — review monetisation or design decisions driving this sentiment  `);
    lines.push(`• Consider UX changes, tooltips, or in-app communication to address the concern  `);
    lines.push(`• Monitor trend across future uploads to check if sentiment is worsening  `);
    lines.push("");
    lines.push(`---\n`);
    lines.push(`### Labels\n`);
    lines.push(`\`user-complaint\` \`${cluster.severity}\` \`user-reported\` \`app-reviews\` \`ai-detected\``);
    return lines.join("\n");
  }

  // ═══════════════════════════════════════════════════════════════════════════
  //  BUG SUBTYPES — crash / ad / login / payment / performance / gameplay / ui / generic bug
  // ═══════════════════════════════════════════════════════════════════════════
  lines.push(`## ${typeEmoji} ${sev} Issue: ${title}\n`);
  metaBlock();

  // Summary
  lines.push(`---\n`);
  lines.push(`### Summary\n`);
  if (cluster.rca_hypothesis) {
    lines.push(cluster.rca_hypothesis);
  } else {
    const summaryByType: Partial<Record<ClusterType, string>> = {
      crash:       `Users are reporting that the application **crashes or becomes unresponsive**, preventing them from using the app entirely.`,
      ad:          `Users are reporting problems related to **advertisement functionality** — ads are not loading, not rewarding, or disrupting normal gameplay flow.`,
      login:       `Users are unable to **sign in or access their accounts**, blocking all app functionality that requires authentication.`,
      payment:     `Users are experiencing issues with **in-app purchases or billing** — transactions failing, purchases not being credited, or unexpected charges.`,
      performance: `Users are reporting that the app is **slow, laggy, or unusually draining battery**, degrading the overall experience.`,
      gameplay:    `Users are reporting that **a core gameplay mechanic or feature is missing or broken**, disrupting normal progression.`,
      ui:          `Users are encountering **visual or layout issues** — broken buttons, overlapping elements, or rendering errors across affected devices.`,
      bug:         `Users are reporting that **the application is not functioning correctly** in the current version.`,
    };
    lines.push(summaryByType[clusterType] ?? summaryByType.bug!);
    lines.push(`\nThe issue appears across ${cluster.review_count} independent reviews in the latest ingestion batch.`);
  }
  lines.push("");

  // Evidence
  evidenceBlock();

  // Impact
  lines.push(`---\n`);
  lines.push(`### Impact\n`);
  const impactByType: Partial<Record<ClusterType, string[]>> = {
    crash:       ["Users are unable to open or use the application", "Potential for significant user drop-off and store rating decline"],
    ad:          ["Players may be unable to watch ads or access ad-gated content", "Possible revenue impact if ad delivery is failing at scale"],
    login:       ["Users are locked out of their accounts, blocking all app functionality", "Risk of account abandonment and negative store reviews"],
    payment:     ["Users may be unable to complete purchases or access purchased content", "Direct revenue impact and potential chargeback exposure"],
    performance: ["Degraded user experience impacting engagement and session length", "Elevated uninstall risk among performance-sensitive users"],
    gameplay:    ["Core gameplay loop or progression is blocked for affected users", "Increased churn risk — engaged users are most likely to notice and report"],
    ui:          ["UI elements broken or rendering incorrectly across affected devices", "Impacts first-impression quality and perceived app polish"],
    bug:         ["Users are experiencing friction in core app functionality", "Risk of negative store reviews and reduced retention"],
  };
  const impacts = impactByType[clusterType] ?? impactByType.bug!;
  impacts.forEach((b) => lines.push(`• ${b}  `));
  lines.push(`• ${sig.volumeDesc}  `);
  if (cluster.severity === "critical" || cluster.severity === "high")
    lines.push(`• **Requires immediate engineering attention**  `);
  lines.push("");

  // Investigation — only for critical / high / medium; skip for low generic bugs
  const skipInvestigation = cluster.severity === "low" && clusterType === "bug";
  if (!skipInvestigation) {
    lines.push(`---\n`);
    lines.push(`### Suggested Investigation Areas\n`);
    const investigationByType: Partial<Record<ClusterType, string[]>> = {
      crash: [
        "Recent app update regression — compare crash logs before/after last release",
        "Native crash reporter (Firebase Crashlytics / Sentry) for stack traces",
        "Memory pressure or ANR reports on affected devices",
        "Test on low-memory devices and OS versions matching most reports",
      ],
      ad: [
        "Ad SDK integration and mediation layer configuration",
        "Network request failures to ad provider endpoints",
        "Ad inventory or provider outage — check SDK dashboard",
        "Client-side rendering issues or WebView compatibility",
      ],
      login: [
        "Auth provider availability (OAuth, Firebase Auth, custom backend)",
        "Session token expiry or refresh logic",
        "OTP / email delivery pipeline failures",
        "Backend auth service logs around affected time window",
      ],
      payment: [
        "Payment gateway or in-app billing SDK error codes",
        "Server-side purchase validation endpoint health",
        "Region-specific billing issues or App Store / Play Store policy changes",
        "Receipt validation logic for edge cases (offline purchase, restore)",
      ],
      performance: [
        "Profiling with Android Profiler / Instruments for CPU and memory hotspots",
        "Background process or wake lock abuse draining battery",
        "Excessive network calls or unoptimised asset loading on startup",
        "Frame timing regressions — compare render time before/after last release",
      ],
      gameplay: [
        "Diff game logic between last stable release and current build",
        "Server-side feature flags or remote config changes that may have toggled off functionality",
        "Reproduce reported level or feature on staging to confirm regression",
        "A/B test rollouts that may have unintentionally affected this user cohort",
      ],
      ui: [
        "Test on affected screen sizes and OS versions to identify rendering breakpoint",
        "Recent theme, font, or asset bundle changes that altered layout",
        "Dark mode / system theme edge cases — test with appearance toggled",
        "Inspect view hierarchy with Layout Inspector for overlapping or missing views",
      ],
      bug: [
        "Review recent deployments or configuration changes for regressions",
        "Cross-reference with server error logs around the affected time window",
        "Reproduce on affected device / OS version combinations",
      ],
    };
    const hints = investigationByType[clusterType] ?? investigationByType.bug!;
    hints.forEach((b) => lines.push(`• ${b}  `));
    if (cluster.keywords?.length)
      lines.push(`• Keywords from clustered reviews: ${cluster.keywords.slice(0, 6).map((k) => `\`${k}\``).join(", ")}  `);
    lines.push("");
  }

  // Labels
  lines.push(`---\n`);
  lines.push(`### Labels\n`);
  const labelList = ["`bug`", `\`${cluster.severity}\``, "`user-reported`", "`app-reviews`", "`ai-detected`"];
  if (cluster.regression_detected) labelList.push("`regression`");
  lines.push(labelList.join(" "));

  return lines.join("\n");
}

// Strips any GitHub URL form down to bare owner/repo
function sanitizeRepo(input: string): string {
  return input
    .trim()
    .replace(/\.git$/i, "")                           // strip .git suffix
    .replace(/^https?:\/\/github\.com\//i, "")       // strip https://github.com/
    .replace(/^github\.com\//i, "")                   // strip github.com/
    .replace(/^git@github\.com:/i, "")               // strip SSH form git@github.com:
    .replace(/\/+$/, "");                             // strip trailing slashes
}

// ─────────────────────────────── component ────────────────────────────────────

export function TicketExportModal({ cluster, appName, onClose }: Props) {
  const [tab, setTab] = useState<Tab>("github");
  const [copied, setCopied] = useState(false);

  // GitHub state
  const [ghRepo, setGhRepo] = useState("");
  const [ghToken, setGhToken] = useState("");
  const [ghLoading, setGhLoading] = useState(false);
  const [ghResult, setGhResult] = useState<{ url: string } | null>(null);
  const [ghError, setGhError] = useState("");

  // Linear state
  const [linKey, setLinKey] = useState("");
  const [linTeam, setLinTeam] = useState("");
  const [linLoading, setLinLoading] = useState(false);
  const [linResult, setLinResult] = useState<{
    identifier: string;
    url: string;
  } | null>(null);
  const [linError, setLinError] = useState("");

  const title = cleanTitle(cluster.title);
  const issueTitle = `[${cluster.severity.toUpperCase()}] ${title} (~${cluster.review_count} users)`;
  const markdown = buildMarkdown(cluster, appName);

  // ── copy ──
  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2200);
  }, [markdown]);

  // ── GitHub ──
  const handleGitHub = async () => {
    const repo = sanitizeRepo(ghRepo);
    if (!repo.includes("/") || !ghToken) return;
    setGhRepo(repo); // normalise display value too
    setGhLoading(true);
    setGhError("");
    setGhResult(null);
    try {
      const res = await fetch(
        `https://api.github.com/repos/${repo}/issues`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${ghToken}`,
            "Content-Type": "application/json",
            Accept: "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
          },
          body: JSON.stringify({
            title: issueTitle,
            body: markdown,
            labels: [
              "bug",
              cluster.severity,
              "user-reported",
              ...(cluster.regression_detected ? ["regression"] : []),
            ],
          }),
        }
      );
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.message ?? `HTTP ${res.status}`);
      }
      const data = await res.json();
      setGhResult({ url: data.html_url });
    } catch (e: unknown) {
      setGhError(e instanceof Error ? e.message : "Failed to create issue");
    } finally {
      setGhLoading(false);
    }
  };

  // ── Linear ──
  const handleLinear = async () => {
    if (!linKey || !linTeam) return;
    setLinLoading(true);
    setLinError("");
    setLinResult(null);
    try {
      const priorityMap: Record<string, number> = {
        critical: 1,
        high: 2,
        medium: 3,
        low: 4,
      };
      const res = await fetch("https://api.linear.app/graphql", {
        method: "POST",
        headers: {
          Authorization: linKey,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: `
            mutation CreateIssue($input: IssueCreateInput!) {
              issueCreate(input: $input) {
                success
                issue { id identifier title url }
              }
            }
          `,
          variables: {
            input: {
              title: issueTitle,
              description: markdown,
              teamId: linTeam,
              priority: priorityMap[cluster.severity] ?? 3,
            },
          },
        }),
      });
      const data = await res.json();
      if (data.errors) throw new Error(data.errors[0]?.message ?? "GraphQL error");
      const issue = data.data?.issueCreate?.issue;
      if (!issue) throw new Error("Issue creation returned empty — check Team ID");
      setLinResult({ identifier: issue.identifier, url: issue.url });
    } catch (e: unknown) {
      setLinError(e instanceof Error ? e.message : "Failed to create issue");
    } finally {
      setLinLoading(false);
    }
  };

  const sevBorder: Record<string, string> = {
    critical: "border-red-500/30",
    high: "border-orange-500/30",
    medium: "border-yellow-500/30",
    low: "border-blue-500/30",
  };
  const sevBg: Record<string, string> = {
    critical: "bg-red-500/8",
    high: "bg-orange-500/8",
    medium: "bg-yellow-500/8",
    low: "bg-blue-500/8",
  };
  const sevText: Record<string, string> = {
    critical: "text-red-400",
    high: "text-orange-400",
    medium: "text-yellow-400",
    low: "text-blue-400",
  };

  return (
    <AnimatePresence>
      <div
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        onClick={onClose}
      >
        {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="absolute inset-0 bg-black/75 backdrop-blur-sm"
        />

        {/* Panel */}
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 10 }}
          transition={{ duration: 0.18, ease: "easeOut" }}
          className="relative z-10 w-full max-w-xl bg-[#0a0a0a] border border-neutral-800 rounded-2xl shadow-2xl overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-800/80">
            <div className="flex items-center gap-3 min-w-0">
              <div
                className={`w-8 h-8 rounded-lg border flex items-center justify-center flex-shrink-0 ${sevBg[cluster.severity]} ${sevBorder[cluster.severity]}`}
              >
                <Ticket className={`w-4 h-4 ${sevText[cluster.severity]}`} />
              </div>
              <div className="min-w-0">
                <p className="font-semibold text-white text-base">Export Ticket</p>
                <p className="text-xs text-neutral-500 truncate">{title}</p>
              </div>
            </div>
            <div className="flex items-center gap-3 flex-shrink-0">
              <span
                className={`text-[11px] font-black px-2 py-0.5 rounded-full border ${sevText[cluster.severity]} ${sevBg[cluster.severity]} ${sevBorder[cluster.severity]}`}
              >
                {cluster.severity.toUpperCase()}
              </span>
              <button
                onClick={onClose}
                className="text-neutral-600 hover:text-white transition-colors"
              >
                <X className="w-4.5 h-4.5" />
              </button>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex border-b border-neutral-800/80">
            {(
              [
                { key: "github", label: "GitHub Issues", icon: <Github className="w-3.5 h-3.5" /> },
                { key: "linear", label: "Linear", icon: <span className="text-sm leading-none">◈</span> },
                { key: "copy", label: "Copy Markdown", icon: <Copy className="w-3.5 h-3.5" /> },
              ] as { key: Tab; label: string; icon: React.ReactNode }[]
            ).map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`flex-1 flex items-center justify-center gap-1.5 py-3 text-sm font-semibold transition-all ${
                  tab === t.key
                    ? "text-white border-b-2 border-orange-500 bg-orange-500/4"
                    : "text-neutral-500 hover:text-neutral-300"
                }`}
              >
                {t.icon}
                {t.label}
              </button>
            ))}
          </div>

          {/* Body */}
          <div className="p-5">
            {/* ── GitHub ── */}
            {tab === "github" && (
              <div className="space-y-3.5">
                <p className="text-xs text-neutral-500 leading-relaxed">
                  Creates a GitHub Issue with labels{" "}
                  <code className="bg-neutral-800 px-1 py-0.5 rounded text-neutral-300">
                    bug
                  </code>{" "}
                  <code className="bg-neutral-800 px-1 py-0.5 rounded text-neutral-300">
                    {cluster.severity}
                  </code>{" "}
                  <code className="bg-neutral-800 px-1 py-0.5 rounded text-neutral-300">
                    user-reported
                  </code>
                  . Labels are created automatically if missing.
                </p>
                <div>
                  <label className="block text-xs text-neutral-400 mb-1.5 font-semibold uppercase tracking-wide">
                    Repository
                  </label>
                  <input
                    value={ghRepo}
                    onChange={(e) => setGhRepo(sanitizeRepo(e.target.value))}
                    placeholder="owner/repo — e.g. acme-corp/mobile-app"
                    className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3.5 py-2.5 text-base text-white placeholder:text-neutral-600 focus:border-orange-500/60 focus:outline-none transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-xs text-neutral-400 mb-1.5 font-semibold uppercase tracking-wide">
                    Personal Access Token
                  </label>
                  <input
                    type="password"
                    value={ghToken}
                    onChange={(e) => setGhToken(e.target.value)}
                    placeholder="ghp_..."
                    className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3.5 py-2.5 text-base text-white placeholder:text-neutral-600 focus:border-orange-500/60 focus:outline-none transition-colors"
                  />
                  <p className="text-[11px] text-neutral-600 mt-1">
                    Needs <code className="bg-neutral-900 px-0.5">repo</code>{" "}
                    scope. Used only in this browser — never sent to our servers.
                  </p>
                </div>
                {ghError && (
                  <div className="flex items-start gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2.5">
                    <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                    {ghError}
                  </div>
                )}
                {ghResult ? (
                  <a
                    href={ghResult.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 text-base text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-xl px-4 py-3 hover:bg-emerald-500/15 transition-colors"
                  >
                    <Check className="w-4 h-4" />
                    Issue created — open in GitHub
                    <ExternalLink className="w-3.5 h-3.5 ml-auto" />
                  </a>
                ) : (
                  <button
                    onClick={handleGitHub}
                    disabled={
                      ghLoading || !ghRepo.includes("/") || !ghToken
                    }
                    className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 hover:border-neutral-600 text-base font-semibold text-white disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                  >
                    {ghLoading ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Github className="w-4 h-4" />
                    )}
                    {ghLoading ? "Creating issue…" : "Create GitHub Issue"}
                  </button>
                )}
              </div>
            )}

            {/* ── Linear ── */}
            {tab === "linear" && (
              <div className="space-y-3.5">
                <p className="text-xs text-neutral-500 leading-relaxed">
                  Creates a Linear issue. Priority is auto-mapped: Critical→P1,
                  High→P2, Medium→P3, Low→P4.
                </p>
                <div>
                  <label className="block text-xs text-neutral-400 mb-1.5 font-semibold uppercase tracking-wide">
                    API Key
                  </label>
                  <input
                    type="password"
                    value={linKey}
                    onChange={(e) => setLinKey(e.target.value)}
                    placeholder="lin_api_..."
                    className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3.5 py-2.5 text-base text-white placeholder:text-neutral-600 focus:border-orange-500/60 focus:outline-none transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-xs text-neutral-400 mb-1.5 font-semibold uppercase tracking-wide">
                    Team ID
                  </label>
                  <input
                    value={linTeam}
                    onChange={(e) => setLinTeam(e.target.value)}
                    placeholder="e.g. a1b2c3d4e5f6..."
                    className="w-full bg-neutral-900 border border-neutral-700 rounded-lg px-3.5 py-2.5 text-base text-white placeholder:text-neutral-600 focus:border-orange-500/60 focus:outline-none transition-colors"
                  />
                  <p className="text-[11px] text-neutral-600 mt-1">
                    Linear → Settings → Teams → copy the UUID from the URL.
                    Keys are never stored.
                  </p>
                </div>
                {linError && (
                  <div className="flex items-start gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2.5">
                    <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                    {linError}
                  </div>
                )}
                {linResult ? (
                  <a
                    href={linResult.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 text-base text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-xl px-4 py-3 hover:bg-emerald-500/15 transition-colors"
                  >
                    <Check className="w-4 h-4" />
                    {linResult.identifier} created — open in Linear
                    <ExternalLink className="w-3.5 h-3.5 ml-auto" />
                  </a>
                ) : (
                  <button
                    onClick={handleLinear}
                    disabled={linLoading || !linKey || !linTeam}
                    className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 hover:border-neutral-600 text-base font-semibold text-white disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                  >
                    {linLoading ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <span className="text-lg leading-none">◈</span>
                    )}
                    {linLoading ? "Creating issue…" : "Create Linear Issue"}
                  </button>
                )}
              </div>
            )}

            {/* ── Copy Markdown ── */}
            {tab === "copy" && (
              <div className="space-y-3">
                <p className="text-xs text-neutral-500">
                  Paste into Jira, Notion, Confluence, or any markdown editor.
                </p>
                <pre className="bg-neutral-900 border border-neutral-800 rounded-xl p-4 text-xs text-neutral-300 overflow-y-auto max-h-64 font-mono leading-relaxed whitespace-pre-wrap">
                  {markdown}
                </pre>
                <button
                  onClick={handleCopy}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 hover:border-neutral-600 text-base font-semibold text-white transition-all"
                >
                  {copied ? (
                    <Check className="w-4 h-4 text-emerald-400" />
                  ) : (
                    <Copy className="w-4 h-4" />
                  )}
                  {copied ? "Copied!" : "Copy to Clipboard"}
                </button>
              </div>
            )}
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
