"use client";

/**
 * SpotlightCard - Mouse-tracking spotlight effect card
 * =====================================================
 * A radial gradient 'spotlight' follows the mouse cursor on hover.
 * Used for feature cards and ticket displays.
 */

import { useRef } from "react";
import { motion, useMotionTemplate, useMotionValue } from "framer-motion";
import { cn } from "@/lib/utils";

interface SpotlightCardProps {
  children: React.ReactNode;
  className?: string;
  spotlightColor?: string;
}

export function SpotlightCard({
  children,
  className,
  spotlightColor = "rgba(255, 46, 0, 0.15)",
}: SpotlightCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  function handleMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    if (!cardRef.current) return;
    const { left, top } = cardRef.current.getBoundingClientRect();
    mouseX.set(e.clientX - left);
    mouseY.set(e.clientY - top);
  }

  const spotlightBackground = useMotionTemplate`
    radial-gradient(
      350px circle at ${mouseX}px ${mouseY}px,
      ${spotlightColor},
      transparent 80%
    )
  `;

  return (
    <motion.div
      ref={cardRef}
      className={cn(
        "group relative overflow-hidden rounded-2xl border border-white/5 bg-black/40 backdrop-blur-xl",
        "transition-colors duration-300 hover:border-white/10",
        className
      )}
      onMouseMove={handleMouseMove}
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.5 }}
    >
      {/* Spotlight overlay */}
      <motion.div
        className="pointer-events-none absolute -inset-px opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{ background: spotlightBackground }}
      />

      {/* Noise texture */}
      <div className="pointer-events-none absolute inset-0 opacity-[0.02] mix-blend-overlay">
        <div className="noise-overlay" />
      </div>

      {/* Content */}
      <div className="relative z-10">{children}</div>
    </motion.div>
  );
}

export default SpotlightCard;
