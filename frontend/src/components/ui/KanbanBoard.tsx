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
import { useRef, useEffect, useState } from "react";

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
        status="fresh"
        onDropTicket={onStatusChange}
        movingId={movingId}
      />
      <KanbanColumn
        title="Fixing"
        icon={<Wrench className="w-5 h-5 text-white" />}
        color="orange"
        tickets={fixingTickets}
        status="fixing"
        onDropTicket={onStatusChange}
        movingId={movingId}
      />
      <KanbanColumn
        title="Resolved"
        icon={<CheckCircle2 className="w-5 h-5 text-white" />}
        color="green"
        tickets={resolvedTickets}
        status="resolved"
        onDropTicket={onStatusChange}
        movingId={movingId}
      />
    </div>
  );
}

export default KanbanBoard;
