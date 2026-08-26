"use client";

/**
 * AgentAnalysisPanel
 * ===================
 * Visible, glanceable surface for the LangGraph RCA agent's work — the
 * reasoning steps it ran, precedent it found via hybrid search, and the
 * RAGAS quality scores. Previously this data only existed as prose buried
 * inside a markdown export; this renders it as real badges/meters instead.
 */

import { motion } from "framer-motion";
import { CheckCircle2, Search, Brain, ShieldQuestion, FileCheck2, Sparkles } from "lucide-react";
import type { ComponentType } from "react";
import type { AgentMetadata } from "@/lib/api-client";

const STEP_META: Record<string, { label: string; icon: ComponentType<{ className?: string }> }> = {
  investigate: { label: "Investigate", icon: Search },
  retrieve_similar: { label: "Search precedent", icon: Sparkles },
  hypothesize: { label: "Hypothesize", icon: Brain },
  critique: { label: "Self-critique", icon: ShieldQuestion },
  finalize: { label: "Finalize", icon: FileCheck2 },
};

function scoreColor(score: number): { text: string; bar: string; bg: string } {
  if (score >= 0.7) return { text: "text-emerald-400", bar: "from-emerald-500 to-green-400", bg: "bg-emerald-500/10" };
  if (score >= 0.4) return { text: "text-yellow-400", bar: "from-yellow-500 to-amber-400", bg: "bg-yellow-500/10" };
  return { text: "text-red-400", bar: "from-red-500 to-orange-400", bg: "bg-red-500/10" };
}

const severityBadge: Record<string, string> = {
  CRITICAL: "text-red-400 bg-red-500/15 border-red-500/30",
  HIGH: "text-orange-400 bg-orange-500/15 border-orange-500/30",
  MEDIUM: "text-yellow-400 bg-yellow-500/15 border-yellow-500/30",
  LOW: "text-blue-400 bg-blue-500/15 border-blue-500/30",
};

export function AgentAnalysisPanel({
  metadata,
  accentColor,
}: {
  metadata: AgentMetadata;
  accentColor: string;
}) {
  const scores = metadata.eval_scores;

  return (
    <div className="p-4 bg-gradient-to-br from-purple-500/[0.06] to-transparent border-b border-white/5">
      <div className="flex items-center justify-between mb-3">
        <p className={`text-xs ${accentColor} font-semibold uppercase tracking-wider flex items-center gap-1.5`}>
          <Sparkles className="w-3.5 h-3.5" />
          AI Agent Analysis
        </p>
        <span className="text-[10px] text-neutral-500 font-mono">
          confidence {(metadata.confidence * 100).toFixed(0)}%
        </span>
      </div>

      {/* Reasoning pipeline — visual proof of the multi-step agent run */}
      <div className="flex items-center gap-1 mb-4 overflow-x-auto pb-1">
        {metadata.agent_steps.map((step, i) => {
          const meta = STEP_META[step] ?? { label: step, icon: CheckCircle2 };
          const Icon = meta.icon;
          return (
            <motion.div
              key={step}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06 }}
              className="flex items-center gap-1 flex-shrink-0"
            >
              <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-white/5 border border-white/10">
                <Icon className="w-3 h-3 text-purple-400" />
                <span className="text-[10px] text-neutral-300 whitespace-nowrap">{meta.label}</span>
                <CheckCircle2 className="w-2.5 h-2.5 text-emerald-400" />
              </div>
              {i < metadata.agent_steps.length - 1 && (
                <div className="w-3 h-px bg-white/10 flex-shrink-0" />
              )}
            </motion.div>
          );
        })}
      </div>

      {/* Hypothesis meta */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <span className="text-[10px] uppercase tracking-wide text-neutral-500">Likelihood</span>
        <span className="text-xs font-semibold text-neutral-200 capitalize">{metadata.likelihood}</span>
        <span className="text-neutral-700">·</span>
        <span className="text-[10px] uppercase tracking-wide text-neutral-500">Scope</span>
        <span className="text-xs font-semibold text-neutral-200 capitalize">{metadata.scope}</span>
        <span className="text-neutral-700">·</span>
        <span
          className={`text-[10px] font-black px-2 py-0.5 rounded-full border ${severityBadge[metadata.suggested_severity] ?? severityBadge.LOW}`}
          title={metadata.severity_reason}
        >
          suggests {metadata.suggested_severity}
        </span>
      </div>

      {/* Similar issues found via hybrid search + reranking */}
      <div className="mb-4">
        <p className="text-[10px] uppercase tracking-wide text-neutral-500 mb-1.5">
          Similar issues found (hybrid search + reranking)
        </p>
        {metadata.similar_issues.length === 0 ? (
          <p className="text-xs text-neutral-500 italic">None found — new issue category.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {metadata.similar_issues.map((issue) => (
              <span
                key={issue.cluster_id}
                className="text-[10px] px-2 py-1 rounded-md bg-white/5 border border-white/10 text-neutral-300"
                title={`${issue.severity} · ${issue.status}`}
              >
                {issue.title}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* RAGAS quality scores */}
      {scores && (
        <div>
          <div className="grid grid-cols-2 gap-3 mb-2">
            {([
              ["Faithfulness", scores.faithfulness],
              ["Answer Relevancy", scores.answer_relevancy],
            ] as const).map(([label, value]) => {
              const c = scoreColor(value);
              return (
                <div key={label} className={`rounded-lg p-2.5 ${c.bg}`}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] text-neutral-400">{label}</span>
                    <span className={`text-xs font-bold ${c.text}`}>{(value * 100).toFixed(0)}%</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${value * 100}%` }}
                      transition={{ duration: 0.6, ease: "easeOut" }}
                      className={`h-full rounded-full bg-gradient-to-r ${c.bar}`}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Why THIS cluster scored this way — concrete, not generic. When
              null, that's the NVIDIA free-tier rate limit (40 req/min) —
              the scores above are still real, just the extra explanation
              call got throttled. Say that plainly instead of showing
              nothing or a generic-looking failure string. */}
          {scores.reasoning ? (
            <p className="text-[10px] text-neutral-400 leading-relaxed mb-2 italic">
              {scores.reasoning}
            </p>
          ) : (
            <p className="text-[10px] text-neutral-600 leading-relaxed mb-2">
              Explanation unavailable (API rate limit) — the scores above are still accurate.
            </p>
          )}

          {/* Generic glossary, kept last/smallest so it doesn't compete with the real signal above */}
          <p className="text-[9px] text-neutral-600 leading-relaxed">
            <span className="text-neutral-500 font-semibold">What these mean:</span>{" "}
            Faithfulness = is this explanation actually backed by the reviews, or is it guessing?{" "}
            Answer Relevancy = does it actually address the reported issue?
          </p>
        </div>
      )}

      {metadata.trace_id && (
        <p className="mt-3 text-[9px] text-neutral-600 font-mono truncate" title={metadata.trace_id}>
          trace: {metadata.trace_id}
        </p>
      )}
    </div>
  );
}
