"use client";

/**
 * KanbanBoard - 5-Column Ticket Board
 * ====================================
 * Columns: Fresh Roast (Red), Assigned (Purple), Fixing (Orange),
 *          Resolved (Green), Won't Fix (Gray)
 * Features: Drag-n-drop ready, Framer Motion animations, ticket grouping
 *
 * Tickets arrive pre-sorted by the caller (fused priority score --
 * severity + AI faithfulness + regression + volume, same formula as the
 * backend's /triage-queue endpoint) -- this component just groups by
 * status and renders in the order it's given, it doesn't re-sort.
 */

import { motion, AnimatePresence, LayoutGroup } from "framer-motion";
import { Flame, UserCheck, Wrench, CheckCircle2, XCircle, MousePointer2, X } from "lucide-react";
import { TicketCard } from "./TicketCard";
import { cn } from "@/lib/utils";
import { useRef, useEffect, useState } from "react";

const DRAG_HINT_DISMISSED_KEY = "roast_kanban_drag_hint_dismissed";

// Ticket type matching backend schema
export interface Ticket {
  id: string;
  title: string;
  summary: string;
  severity: "critical" | "high" | "medium" | "low";
  cluster_id: string;
  app_version?: string;
  device_type?: string;
  review_count: number;
  status: "fresh" | "assigned" | "fixing" | "resolved" | "wont_fix";
  /** Fused triage score (severity + AI faithfulness + regression + volume) -- same formula as /triage-queue. Optional: only populated where the caller computes it (see dashboard/page.tsx). */
  priorityScore?: number;
  /** The four components priorityScore is built from, for a visual breakdown (Roast Arena's power bar). */
  priorityBreakdown?: {
    severityWeight: number;
    faithfulness: number;
    regressionBoost: number;
    velocity: number;
  };
  regressionDetected?: boolean;
  regressionOfTitle?: string | null;
  regressionConfidence?: number | null;
}

interface KanbanColumnProps {
  title: string;
  icon: React.ReactNode;
  color: "red" | "purple" | "orange" | "green" | "gray";
  tickets: Ticket[];
  className?: string;
  status: Ticket["status"];
  onDropTicket?: (ticketId: string, newStatus: Ticket["status"]) => void;
  movingId?: string | null;
}

function KanbanColumn({ title, icon, color, tickets, className, status, onDropTicket, movingId }: KanbanColumnProps) {
  const hasAnimated = useRef(false);
  const [isDragOver, setIsDragOver] = useState(false);

  useEffect(() => {
    // Mark as animated after first render
    if (!hasAnimated.current && tickets.length > 0) {
      hasAnimated.current = true;
    }
  }, [tickets.length]);

  const colorStyles = {
    red: {
      border: "border-red-500/30",
      bg: "bg-red-500/5",
      header: "from-red-600 to-red-800",
      glow: "shadow-red-500/20",
      count: "bg-red-500/20 text-red-400",
    },
    purple: {
      border: "border-purple-500/30",
      bg: "bg-purple-500/5",
      header: "from-purple-500 to-violet-700",
      glow: "shadow-purple-500/20",
      count: "bg-purple-500/20 text-purple-400",
    },
    orange: {
      border: "border-orange-500/30",
      bg: "bg-orange-500/5",
      header: "from-orange-500 to-amber-600",
      glow: "shadow-orange-500/20",
      count: "bg-orange-500/20 text-orange-400",
    },
    green: {
      border: "border-emerald-500/30",
      bg: "bg-emerald-500/5",
      header: "from-emerald-500 to-green-600",
      glow: "shadow-emerald-500/20",
      count: "bg-emerald-500/20 text-emerald-400",
    },
    gray: {
      border: "border-neutral-500/30",
      bg: "bg-neutral-500/5",
      header: "from-neutral-600 to-neutral-800",
      glow: "shadow-neutral-500/20",
      count: "bg-neutral-500/20 text-neutral-400",
    },
  };

  const styles = colorStyles[color];

  return (
    <div
      className={cn(
        "flex flex-col rounded-2xl border backdrop-blur-sm transition-colors",
        isDragOver ? "border-white/40 bg-white/[0.03]" : [styles.border, styles.bg],
        className
      )}
      onDragOver={onDropTicket ? (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; setIsDragOver(true); } : undefined}
      onDragLeave={onDropTicket ? () => setIsDragOver(false) : undefined}
      onDrop={onDropTicket ? (e) => {
        e.preventDefault();
        setIsDragOver(false);
        const ticketId = e.dataTransfer.getData("text/plain");
        if (ticketId) onDropTicket(ticketId, status);
      } : undefined}
    >
      {/* Column Header */}
      <div className="p-4 border-b border-white/5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className={cn(
                "w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br shadow-lg",
                styles.header,
                styles.glow
              )}
            >
              {icon}
            </div>
            <h3 className="font-bold text-white">{title}</h3>
          </div>
          <span
            className={cn(
              "px-2.5 py-1 rounded-full text-xs font-semibold",
              styles.count
            )}
          >
            {tickets.length}
          </span>
        </div>
      </div>

      {/* Tickets Container */}
      <div className="flex-1 p-3 space-y-3 overflow-y-auto max-h-[calc(100vh-280px)] scrollbar-thin">
        {tickets.map((ticket, index) => (
          <div key={ticket.id} className={movingId === ticket.id ? "opacity-40 pointer-events-none" : undefined}>
            <TicketCard
              id={ticket.id}
              title={ticket.title}
              summary={ticket.summary}
              severity={ticket.severity}
              version={ticket.app_version}
              device={ticket.device_type}
              evidenceCount={ticket.review_count}
              draggable={!!onDropTicket}
            />
          </div>
        ))}

        {tickets.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-4">
              {icon}
            </div>
            <p className="text-sm text-neutral-500">
              {isDragOver ? "Drop here" : "No tickets here"}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

interface KanbanBoardProps {
  tickets: Ticket[];
  className?: string;
  /** Drag a card into a different column -- omit to keep the board read-only. */
  onStatusChange?: (ticketId: string, newStatus: Ticket["status"]) => void;
  /** Ticket currently mid-save (dims the card, blocks re-dragging it). */
  movingId?: string | null;
}

export function KanbanBoard({ tickets, className, onStatusChange, movingId }: KanbanBoardProps) {
  // Group tickets by status -- order within each group is whatever the
  // caller already sorted `tickets` into (see dashboard/page.tsx).
  const freshTickets = tickets.filter((t) => t.status === "fresh");
  const assignedTickets = tickets.filter((t) => t.status === "assigned");
  const fixingTickets = tickets.filter((t) => t.status === "fixing");
  const resolvedTickets = tickets.filter((t) => t.status === "resolved");
  const wontFixTickets = tickets.filter((t) => t.status === "wont_fix");

  // One-time discoverability hint: dragging cards between columns isn't
  // obvious from looking at the board (no visible affordance until you
  // hover a card), and plenty of users have never touched a Jira/Trello-
  // style board to already know the pattern. Shown once, dismissed
  // permanently via localStorage -- never nags on repeat visits.
  const [showDragHint, setShowDragHint] = useState(false);
  useEffect(() => {
    if (!onStatusChange) return;
    try {
      if (!window.localStorage.getItem(DRAG_HINT_DISMISSED_KEY)) {
        setShowDragHint(true);
      }
    } catch {
      // localStorage unavailable (private mode etc.) -- just skip the hint
      // rather than risk it reappearing every render.
    }
  }, [onStatusChange]);

  const dismissDragHint = () => {
    setShowDragHint(false);
    try {
      window.localStorage.setItem(DRAG_HINT_DISMISSED_KEY, "1");
    } catch {
      // best-effort only
    }
  };

  return (
    <div className={className}>
      <AnimatePresence>
        {showDragHint && (
          <motion.div
            initial={{ opacity: 0, height: 0, marginBottom: 0 }}
            animate={{ opacity: 1, height: "auto", marginBottom: 16 }}
            exit={{ opacity: 0, height: 0, marginBottom: 0 }}
            className="overflow-hidden"
          >
            <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-orange-500/10 border border-orange-500/20 text-sm text-orange-200">
              <MousePointer2 className="w-4 h-4 shrink-0 text-orange-400" />
              <span className="flex-1">
                Tip: drag a card into another column to change its status.
              </span>
              <button
                onClick={dismissDragHint}
                className="p-1 rounded-md hover:bg-white/10 transition-colors shrink-0"
                aria-label="Dismiss tip"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex gap-6 h-full overflow-x-auto pb-2">
      <KanbanColumn
        title="Fresh Roast"
        icon={<Flame className="w-5 h-5 text-white" />}
        color="red"
        tickets={freshTickets}
        status="fresh"
        onDropTicket={onStatusChange}
        movingId={movingId}
        className="min-w-[280px] flex-1"
      />
      <KanbanColumn
        title="Assigned"
        icon={<UserCheck className="w-5 h-5 text-white" />}
        color="purple"
        tickets={assignedTickets}
        status="assigned"
        onDropTicket={onStatusChange}
        movingId={movingId}
        className="min-w-[280px] flex-1"
      />
      <KanbanColumn
        title="Fixing"
        icon={<Wrench className="w-5 h-5 text-white" />}
        color="orange"
        tickets={fixingTickets}
        status="fixing"
        onDropTicket={onStatusChange}
        movingId={movingId}
        className="min-w-[280px] flex-1"
      />
      <KanbanColumn
        title="Resolved"
        icon={<CheckCircle2 className="w-5 h-5 text-white" />}
        color="green"
        tickets={resolvedTickets}
        status="resolved"
        onDropTicket={onStatusChange}
        movingId={movingId}
        className="min-w-[280px] flex-1"
      />
      <KanbanColumn
        title="Won't Fix"
        icon={<XCircle className="w-5 h-5 text-white" />}
        color="gray"
        tickets={wontFixTickets}
        status="wont_fix"
        onDropTicket={onStatusChange}
        movingId={movingId}
        className="min-w-[280px] flex-1"
      />
      </div>
    </div>
  );
}

export default KanbanBoard;
