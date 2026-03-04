"use client";

/**
 * CursorGlow - Interactive Cursor Trail
 * ======================================
 * Large radial gradient that follows the cursor with smooth lerp
 */

import { useEffect, useState } from "react";

export function CursorGlow() {
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [targetPosition, setTargetPosition] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setTargetPosition({ x: e.clientX, y: e.clientY });
    };

    window.addEventListener("mousemove", handleMouseMove);

    // Smooth lerp animation
    const animationFrame = () => {
      setPosition((prev) => ({
        x: prev.x + (targetPosition.x - prev.x) * 0.15, // 20px lag
        y: prev.y + (targetPosition.y - prev.y) * 0.15,
      }));
      requestAnimationFrame(animationFrame);
    };

    const animation = requestAnimationFrame(animationFrame);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      cancelAnimationFrame(animation);
    };
  }, [targetPosition]);

  return (
    <div
      className="fixed pointer-events-none z-0"
      style={{
        left: 0,
        top: 0,
        width: "500px",
        height: "500px",
        borderRadius: "50%",
        background: "radial-gradient(circle, rgba(249, 115, 22, 0.08) 0%, transparent 70%)",
        transform: `translate(${position.x - 250}px, ${position.y - 250}px)`,
        transition: "none",
      }}
    />
  );
}
