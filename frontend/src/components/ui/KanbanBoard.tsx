"use client";

/**
 * KanbanBoard - 3-Column Ticket Board
 * ====================================
 * Columns: Fresh Roast (Red), Fixing (Orange), Resolved (Green)
 * Features: Drag-n-drop ready, Framer Motion animations, ticket grouping
 */

import { motion, LayoutGroup } from "framer-motion";
import { Flame, Wrench, CheckCircle2 } from "lucide-react";
import { TicketCard } from "./TicketCard";
import { cn } from "@/lib/utils";

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
  status: "fresh" | "fixing" | "resolved";
}

interface KanbanColumnProps {
  title: string;
  icon: React.ReactNode;
  color: "red" | "orange" | "green";
  tickets: Ticket[];
  className?: string;
}

function KanbanColumn({ title, icon, color, tickets, className }: KanbanColumnProps) {
  const colorStyles = {
    red: {
      border: "border-red-500/30",
      bg: "bg-red-500/5",
      header: "from-red-600 to-red-800",
      glow: "shadow-red-500/20",
      count: "bg-red-500/20 text-red-400",
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
  };

  const styles = colorStyles[color];

  return (
    <motion.div
      layout
      className={cn(
        "flex flex-col rounded-2xl border backdrop-blur-sm",
        styles.border,
        styles.bg,
        className
      )}
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
        <LayoutGroup>
          {tickets.map((ticket, index) => (
            <motion.div
              key={ticket.id}
              layout
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{
                duration: 0.3,
                delay: index * 0.05,
                layout: { type: "spring", stiffness: 300, damping: 30 },
              }}
            >
              <TicketCard
                id={ticket.id}
                title={ticket.title}
                summary={ticket.summary}
                severity={ticket.severity}
                version={ticket.app_version}
                device={ticket.device_type}
                evidenceCount={ticket.review_count}
              />
            </motion.div>
          ))}
        </LayoutGroup>

        {tickets.length === 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center py-12 text-center"
          >
            <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-4">
              {icon}
            </div>
            <p className="text-sm text-neutral-500">No tickets here</p>
          </motion.div>
        )}
      </div>
    </motion.div>
  );
}

interface KanbanBoardProps {
  tickets: Ticket[];
  className?: string;
}

export function KanbanBoard({ tickets, className }: KanbanBoardProps) {
  // Group tickets by status
  const freshTickets = tickets.filter((t) => t.status === "fresh");
  const fixingTickets = tickets.filter((t) => t.status === "fixing");
  const resolvedTickets = tickets.filter((t) => t.status === "resolved");

  return (
    <div
      className={cn(
        "grid grid-cols-1 lg:grid-cols-3 gap-6 h-full",
        className
      )}
    >
      <KanbanColumn
        title="Fresh Roast"
        icon={<Flame className="w-5 h-5 text-white" />}
        color="red"
        tickets={freshTickets}
      />
      <KanbanColumn
        title="Fixing"
        icon={<Wrench className="w-5 h-5 text-white" />}
        color="orange"
        tickets={fixingTickets}
      />
      <KanbanColumn
        title="Resolved"
        icon={<CheckCircle2 className="w-5 h-5 text-white" />}
        color="green"
        tickets={resolvedTickets}
      />
    </div>
  );
}

export default KanbanBoard;
