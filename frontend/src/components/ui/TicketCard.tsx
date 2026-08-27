"use client";

/**
 * TicketCard - Dashboard ticket component
 * =======================================
 * Glassmorphism card with severity-colored border,
 * TextReveal title, and metadata badges.
 */

import { motion } from "framer-motion";
import { Flame, Tag, Smartphone, AlertTriangle, GripVertical } from "lucide-react";
import { cn } from "@/lib/utils";
import { TextReveal } from "./TextReveal";

// ============================================================================
// TYPES
// ============================================================================

export type Severity = "critical" | "high" | "medium" | "low";

export interface TicketCardProps {
  id: string;
  title: string;
  severity: Severity;
  version?: string;
  device?: string;
  evidenceCount: number;
  summary?: string;
  onClick?: () => void;
  className?: string;
  /** Enables native HTML5 drag-and-drop -- the id is what KanbanColumn reads on drop. */
  draggable?: boolean;
}

// ============================================================================
// SEVERITY CONFIG
// ============================================================================

const severityConfig = {
  critical: {
    color: "border-l-red-500",
    bg: "bg-red-500/20",
    text: "text-red-400",
    label: "CRITICAL",
  },
  high: {
    color: "border-l-orange-500",
    bg: "bg-orange-500/20",
    text: "text-orange-400",
    label: "HIGH",
  },
  medium: {
    color: "border-l-yellow-500",
    bg: "bg-yellow-500/20",
    text: "text-yellow-400",
    label: "MEDIUM",
  },
  low: {
    color: "border-l-blue-500",
    bg: "bg-blue-500/20",
    text: "text-blue-400",
    label: "LOW",
  },
};

// ============================================================================
// COMPONENT
// ============================================================================

export function TicketCard({
  id,
  title,
  severity,
  version,
  device,
  evidenceCount,
  summary,
  onClick,
  className,
  draggable,
}: TicketCardProps) {
  const config = severityConfig[severity];

  return (
    <div
      className={cn(
        "group relative cursor-pointer rounded-xl border-l-4 bg-black/30 backdrop-blur-xl",
        "border border-white/5 hover:border-white/10 transition-all duration-200",
        "hover:bg-black/40",
        draggable && "cursor-grab active:cursor-grabbing active:opacity-60 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/40",
        config.color,
        className
      )}
      onClick={onClick}
      draggable={draggable}
      onDragStart={draggable ? (e) => {
        e.dataTransfer.setData("text/plain", id);
        e.dataTransfer.effectAllowed = "move";
      } : undefined}
    >
      {/* Drag handle -- invisible until hovered, so a first-time user
          discovers "this can be dragged" without permanent visual clutter. */}
      {draggable && (
        <div
          className="absolute right-2 top-2 opacity-0 group-hover:opacity-50 transition-opacity duration-150 pointer-events-none"
          aria-hidden="true"
        >
          <GripVertical className="w-4 h-4 text-neutral-400" />
        </div>
      )}

      <div className="p-4 space-y-3">
        {/* Header: Severity + Metadata */}
        <div className="flex items-center gap-2 flex-wrap pr-5">
          <span
            className={cn(
              "px-2 py-0.5 text-xs font-bold rounded",
              config.bg,
              config.text
            )}
          >
            {config.label}
          </span>

          {version && (
            <span className="flex items-center gap-1 text-xs text-neutral-500">
              <Tag className="w-3 h-3" />
              {version}
            </span>
          )}

          {device && (
            <span className="flex items-center gap-1 text-xs text-neutral-500">
              <Smartphone className="w-3 h-3" />
              {device}
            </span>
          )}
        </div>

        {/* Title */}
        <h3 className="font-semibold text-white group-hover:text-orange-400 transition-colors line-clamp-2">
          {title}
        </h3>

        {/* Summary (truncated) */}
        {summary && (
          <p className="text-sm text-neutral-500 italic line-clamp-2">
            {summary}
          </p>
        )}

        {/* Footer: Evidence count */}
        <div className="flex items-center justify-between pt-2 border-t border-white/5">
          <div className="flex items-center gap-1.5 text-orange-500">
            <Flame className="w-4 h-4" />
            <span className="text-sm font-medium">{evidenceCount} roasts</span>
          </div>
          
          {severity === "critical" && (
            <div className="flex items-center gap-1 text-red-500">
              <AlertTriangle className="w-4 h-4" />
              <span className="text-xs font-medium">Urgent</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default TicketCard;
