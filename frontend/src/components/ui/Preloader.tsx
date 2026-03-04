"use client";

/**
 * Preloader - Cinematic Page Load Animation
 * ==========================================
 * Full-screen preloader with fire emoji logo
 * Shows on first page load for ~1.5 seconds
 */

import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useState } from "react";

export function Preloader() {
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Hide preloader after 1.5 seconds
    const timer = setTimeout(() => {
      setIsLoading(false);
    }, 1500);

    return () => clearTimeout(timer);
  }, []);

  return (
    <AnimatePresence>
      {isLoading && (
        <motion.div
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-black"
          initial={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        >
          <motion.div
            className="text-9xl"
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ 
              scale: [0.5, 1.2, 1.0],
              opacity: 1 
            }}
            transition={{ 
              duration: 0.8, 
              ease: [0.34, 1.56, 0.64, 1], // Custom ease-out bounce
              times: [0, 0.6, 1]
            }}
          >
            🔥
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
