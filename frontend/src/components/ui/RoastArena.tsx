"use client";

/**
 * RoastArena - a ranked leaderboard alternative to the Kanban board.
 * ====================================================================
 * The Kanban board answers "what state is this ticket in." This answers
 * a different question: "which of these actually deserves my attention
 * right now" -- using the exact fused priority score the backend's
 * /triage-queue endpoint computes (severity + AI faithfulness + regression
 * signal + log-scaled volume), rendered as a literal power bar broken into
 * its four real components instead of a hidden sort key.
 *
 * Cards duel for rank: framer-motion's `layout` prop turns any reorder
 * (new upload, an AI eval landing, a regression detected) into a visible
 * swap instead of a silent re-sort. Resolving a card is a "KO" -- it
 * animates out of the arena via AnimatePresence rather than just
 * vanishing. A regression on a previously-resolved cluster gets one loud,
 * one-time "back in the arena" entrance the first time it's seen, tracked
 * per-browser via localStorage so it doesn't replay on every reload.
 */

import { motion, AnimatePresence } from "framer-motion";
import { Flame, Trophy, Zap, UserCheck, Wrench, CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { useEffect, useMemo, useState } from "react";
import type { Ticket } from "./KanbanBoard";

const SEEN_REGRESSIONS_KEY = "roast_arena_seen_regressions";

const severityStyles: Record<Ticket["severity"], { text: string; bg: string; ring: string }> = {
  critical: { text: "text-red-400", bg: "bg-red-500/20", ring: "ring-red-500/30" },
  high: { text: "text-orange-400", bg: "bg-orange-500/20", ring: "ring-orange-500/30" },
  medium: { text: "text-yellow-400", bg: "bg-yellow-500/20", ring: "ring-yellow-500/30" },
  low: { text: "text-blue-400", bg: "bg-blue-500/20", ring: "ring-blue-500/30" },
};

const rankStyles = [
  { label: "🥇", glow: "shadow-[0_0_20px_rgba(250,204,21,0.25)]", border: "border-yellow-500/40" },
  { label: "🥈", glow: "shadow-[0_0_16px_rgba(203,213,225,0.18)]", border: "border-slate-400/30" },
  { label: "🥉", glow: "shadow-[0_0_16px_rgba(217,119,6,0.18)]", border: "border-amber-600/30" },
];

const STATUS_ACTIONS: { status: Ticket["status"]; label: string; icon: React.ReactNode }[] = [
  { status: "assigned", label: "Assign", icon: <UserCheck className="w-3.5 h-3.5" /> },
  { status: "fixing", label: "Fixing", icon: <Wrench className="w-3.5 h-3.5" /> },
  { status: "resolved", label: "Resolve", icon: <CheckCircle2 className="w-3.5 h-3.5" /> },
  { status: "wont_fix", label: "Won't fix", icon: <XCircle className="w-3.5 h-3.5" /> },
];

function loadSeenRegressions(): Set<string> {
  try {
    const raw = window.localStorage.getItem(SEEN_REGRESSIONS_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

function saveSeenRegressions(seen: Set<string>) {
  try {
    window.localStorage.setItem(SEEN_REGRESSIONS_KEY, JSON.stringify([...seen]));
  } catch {
    // best-effort only
  }
}

interface PowerBarProps {
  breakdown: NonNullable<Ticket["priorityBreakdown"]>;
  score: number;
  maxScore: number;
}

function PowerBar({ breakdown, score, maxScore }: PowerBarProps) {
  const { severityWeight, faithfulness, regressionBoost, velocity } = breakdown;
  const total = Math.max(severityWeight + faithfulness + regressionBoost + velocity, 0.001);
  const widthPct = Math.max(6, Math.min(100, (score / Math.max(maxScore, 1)) * 100));

  const segments = [
    { key: "severity", value: severityWeight, color: "bg-red-500" },
    { key: "evidence", value: faithfulness, color: "bg-sky-500" },
    { key: "regression", value: regressionBoost, color: "bg-purple-500" },
    { key: "volume", value: velocity, color: "bg-emerald-500" },
  ];

  return (
    <div className="w-full">
      <div className="h-2.5 rounded-full bg-white/5 overflow-hidden" style={{ width: `${widthPct}%` }}>
        <div className="flex h-full">
          {segments.map((seg) => (
            <div
              key={seg.key}
              className={cn(seg.color, "h-full transition-all duration-500")}
              style={{ width: `${(seg.value / total) * 100}%` }}
              title={`${seg.key}: ${seg.value.toFixed(1)}`}
            />
          ))}
        </div>
      </div>
      <div className="flex items-center gap-3 mt-1 text-[10px] text-neutral-500">
        <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-red-500" />severity</span>
        <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-sky-500" />evidence</span>
        <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-purple-500" />regression</span>
        <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />volume</span>
        <span className="ml-auto font-semibold text-neutral-400">{score.toFixed(0)} pts</span>
      </div>
    </div>
  );
}

interface ArenaRowProps {
  ticket: Ticket;
  rank: number;
  maxScore: number;
  isNewReturn: boolean;
  isMoving: boolean;
  onStatusChange?: (ticketId: string, newStatus: Ticket["status"]) => void;
}

function ArenaRow({ ticket, rank, maxScore, isNewReturn, isMoving, onStatusChange }: ArenaRowProps) {
  const sev = severityStyles[ticket.severity];
  const medal = rankStyles[rank];
  const score = ticket.priorityScore ?? 0;

  return (
    <motion.div
      layout
      initial={isNewReturn ? { opacity: 0, x: -40, scale: 0.9 } : { opacity: 0, y: 12 }}
      animate={
        isNewReturn
          ? { opacity: 1, x: 0, scale: 1, boxShadow: ["0 0 0px rgba(239,68,68,0)", "0 0 30px rgba(239,68,68,0.5)", "0 0 0px rgba(239,68,68,0)"] }
          : { opacity: 1, y: 0 }
      }
      exit={{ opacity: 0, scale: 0.85, rotate: -3, transition: { duration: 0.35 } }}
      transition={isNewReturn ? { duration: 1.2 } : { type: "spring", stiffness: 350, damping: 30 }}
      className={cn(
        "relative rounded-xl border bg-black/30 backdrop-blur-xl p-4",
        "border-white/5",
        medal && `${medal.border} ${medal.glow}`,
        isMoving && "opacity-40 pointer-events-none",
        isNewReturn && "border-red-500/40"
      )}
    >
      {isNewReturn && (
        <div className="absolute -top-2.5 left-4 px-2 py-0.5 rounded-full bg-red-500 text-white text-[10px] font-black uppercase tracking-wide flex items-center gap-1">
          <Zap className="w-3 h-3" />
          Back in the arena — fix didn't hold
        </div>
      )}

      <div className="flex items-start gap-3">
        <div className="flex flex-col items-center w-9 shrink-0 pt-0.5">
          {medal ? (
            <span className="text-lg leading-none">{medal.label}</span>
          ) : (
            <span className="text-sm font-black text-neutral-500">#{rank + 1}</span>
          )}
        </div>

        <div className="flex-1 min-w-0 space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={cn("px-2 py-0.5 text-[10px] font-bold rounded", sev.bg, sev.text)}>
              {ticket.severity.toUpperCase()}
            </span>
            {ticket.regressionDetected && !isNewReturn && (
              <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-purple-500/20 text-purple-300">
                FIX DIDN'T HOLD
              </span>
            )}
            <span className="text-xs text-neutral-500 flex items-center gap-1">
              <Flame className="w-3 h-3 text-orange-500" />
              {ticket.review_count} roast{ticket.review_count !== 1 ? "s" : ""}
            </span>
          </div>

          <h4 className="font-semibold text-white leading-snug line-clamp-2">{ticket.title}</h4>

          {ticket.priorityBreakdown && (
            <PowerBar breakdown={ticket.priorityBreakdown} score={score} maxScore={maxScore} />
          )}
        </div>

        {onStatusChange && (
          <div className="flex flex-col gap-1 shrink-0">
            {STATUS_ACTIONS.filter((a) => a.status !== ticket.status).map((action) => (
              <button
                key={action.status}
                onClick={() => onStatusChange(ticket.id, action.status)}
                className="flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-md bg-white/5 hover:bg-white/10 text-neutral-300 hover:text-white transition-colors"
              >
                {action.icon}
                {action.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}

interface RoastArenaProps {
  tickets: Ticket[];
  onStatusChange?: (ticketId: string, newStatus: Ticket["status"]) => void;
  movingId?: string | null;
  className?: string;
}

export function RoastArena({ tickets, onStatusChange, movingId, className }: RoastArenaProps) {
  const [seenRegressions, setSeenRegressions] = useState<Set<string>>(new Set());
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setSeenRegressions(loadSeenRegressions());
    setHydrated(true);
  }, []);

  // Only tickets still actively "in the fight" -- resolved/won't-fix ones
  // exit the arena entirely (see the ringside strip below) rather than
  // cluttering the ranked list they no longer belong in.
  const active = useMemo(
    () => tickets.filter((t) => t.status !== "resolved" && t.status !== "wont_fix"),
    [tickets]
  );
  const ringside = useMemo(
    () => tickets.filter((t) => t.status === "resolved" || t.status === "wont_fix"),
    [tickets]
  );

  const ranked = useMemo(
    () => [...active].sort((a, b) => (b.priorityScore ?? 0) - (a.priorityScore ?? 0)),
    [active]
  );
  const maxScore = ranked.length > 0 ? Math.max(...ranked.map((t) => t.priorityScore ?? 0), 1) : 1;

  // Mark any currently-visible regression as "seen" once hydrated, so its
  // dramatic entrance only plays the first time this browser renders it.
  useEffect(() => {
    if (!hydrated) return;
    const toMark = ranked.filter((t) => t.regressionDetected && !seenRegressions.has(t.id));
    if (toMark.length === 0) return;
    const timer = setTimeout(() => {
      const next = new Set(seenRegressions);
      toMark.forEach((t) => next.add(t.id));
      setSeenRegressions(next);
      saveSeenRegressions(next);
    }, 2500);
    return () => clearTimeout(timer);
  }, [hydrated, ranked, seenRegressions]);

  if (!hydrated) return null;

  return (
    <div className={className}>
      <div className="flex items-center gap-2 mb-4">
        <Trophy className="w-5 h-5 text-yellow-500" />
        <h3 className="font-bold text-white">Roast Arena</h3>
        <span className="text-xs text-neutral-500">— ranked by real impact, not just severity</span>
      </div>

      <div className="space-y-3">
        <AnimatePresence initial={false}>
          {ranked.map((ticket, i) => (
            <ArenaRow
              key={ticket.id}
              ticket={ticket}
              rank={i}
              maxScore={maxScore}
              isNewReturn={!!ticket.regressionDetected && !seenRegressions.has(ticket.id)}
              isMoving={movingId === ticket.id}
              onStatusChange={onStatusChange}
            />
          ))}
        </AnimatePresence>

        {ranked.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-center rounded-xl border border-white/5 bg-black/20">
            <Trophy className="w-10 h-10 text-neutral-700 mb-3" />
            <p className="text-sm text-neutral-500">Nothing in the arena right now — the ring is empty.</p>
          </div>
        )}
      </div>

      {ringside.length > 0 && (
        <div className="mt-8">
          <p className="text-xs font-semibold uppercase tracking-wider text-neutral-600 mb-3">
            Ringside ({ringside.length} settled)
          </p>
          <div className="flex flex-wrap gap-2">
            {ringside.map((t) => (
              <span
                key={t.id}
                className={cn(
                  "px-2.5 py-1 rounded-full text-[11px] border flex items-center gap-1.5",
                  t.status === "resolved"
                    ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/20"
                    : "bg-neutral-500/10 text-neutral-400 border-neutral-500/20"
                )}
                title={t.title}
              >
                {t.status === "resolved" ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                <span className="max-w-[10rem] truncate">{t.title}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default RoastArena;
