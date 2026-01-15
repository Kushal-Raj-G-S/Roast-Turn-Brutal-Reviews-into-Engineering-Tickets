"use client";

/**
 * TicketCard - Dashboard ticket component
 * =======================================
 * Glassmorphism card with severity-colored border,
 * TextReveal title, and metadata badges.
 */

import { motion } from "framer-motion";
import { Flame, Tag, Smartphone, AlertTriangle } from "lucide-react";
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
}: TicketCardProps) {
  const config = severityConfig[severity];

  return (
    <motion.div
      layoutId={`ticket-${id}`}
      className={cn(
        "group cursor-pointer rounded-xl border-l-4 bg-black/30 backdrop-blur-xl",
        "border border-white/5 hover:border-white/10 transition-all duration-200",
        "hover:bg-black/40",
        config.color,
        className
      )}
      onClick={onClick}
      whileHover={{ scale: 1.01, x: 4 }}
      whileTap={{ scale: 0.99 }}
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      transition={{ type: "spring", stiffness: 300, damping: 25 }}
    >
      <div className="p-4 space-y-3">
        {/* Header: Severity + Metadata */}
        <div className="flex items-center gap-2 flex-wrap">
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

        {/* Title with scramble effect */}
        <h3 className="font-semibold text-white group-hover:text-orange-400 transition-colors line-clamp-2">
          <TextReveal text={title} trigger={true} />
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
            <div className="flex items-center gap-1 text-red-500 animate-pulse">
              <AlertTriangle className="w-4 h-4" />
              <span className="text-xs font-medium">Urgent</span>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

export default TicketCard;
