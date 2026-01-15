"use client";

/**
 * TextReveal - Matrix-style scramble text effect
 * ==============================================
 * Characters cycle through random symbols before landing on correct letter.
 */

import { useEffect, useState, useCallback } from "react";
import { cn } from "@/lib/utils";

interface TextRevealProps {
  text: string;
  className?: string;
  delay?: number;
  duration?: number;
  trigger?: boolean;
}

const CHARS = "!@#$%^&*()_+-=[]{}|;':\",./<>?`~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

export function TextReveal({
  text,
  className,
  delay = 0,
  duration = 50,
  trigger = true,
}: TextRevealProps) {
  const [displayText, setDisplayText] = useState(text);
  const [isAnimating, setIsAnimating] = useState(false);

  const scramble = useCallback(() => {
    if (!trigger || isAnimating) return;

    setIsAnimating(true);
    let iteration = 0;
    const maxIterations = text.length;

    const interval = setInterval(() => {
      setDisplayText((prev) => {
        return text
          .split("")
          .map((char, index) => {
            if (char === " ") return " ";
            if (index < iteration) {
              return text[index];
            }
            return CHARS[Math.floor(Math.random() * CHARS.length)];
          })
          .join("");
      });

      iteration += 1 / 3;

      if (iteration >= maxIterations) {
        clearInterval(interval);
        setDisplayText(text);
        setIsAnimating(false);
      }
    }, duration);

    return () => clearInterval(interval);
  }, [text, duration, trigger, isAnimating]);

  useEffect(() => {
    if (!trigger) {
      setDisplayText(text);
      return;
    }

    const timer = setTimeout(() => {
      scramble();
    }, delay);

    return () => clearTimeout(timer);
  }, [delay, scramble, trigger, text]);

  return (
    <span className={cn("font-mono", className)}>
      {displayText}
    </span>
  );
}

export default TextReveal;
