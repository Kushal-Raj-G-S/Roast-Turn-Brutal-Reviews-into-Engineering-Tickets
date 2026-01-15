"use client";

/**
 * EmptyState - Large Dashed Border Dropzone
 * ==========================================
 * Features: Flame icon, upload prompt, file drag support
 */

import { motion } from "framer-motion";
import { Flame, Upload, FileSpreadsheet } from "lucide-react";
import { cn } from "@/lib/utils";
import { useCallback, useState } from "react";

interface EmptyStateProps {
  onFileSelect?: (file: File) => void;
  isLoading?: boolean;
  className?: string;
}

export function EmptyState({ onFileSelect, isLoading = false, className }: EmptyStateProps) {
  const [isDragging, setIsDragging] = useState(false);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);

      const file = e.dataTransfer.files[0];
      if (file && file.type === "text/csv") {
        onFileSelect?.(file);
      }
    },
    [onFileSelect]
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        onFileSelect?.(file);
      }
    },
    [onFileSelect]
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className={cn("w-full", className)}
    >
      <label
        htmlFor="csv-upload"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          "relative flex flex-col items-center justify-center w-full min-h-[400px] rounded-3xl border-2 border-dashed cursor-pointer transition-all duration-300",
          isDragging
            ? "border-orange-500 bg-orange-500/10 scale-[1.02]"
            : "border-neutral-700 bg-neutral-900/50 hover:border-neutral-600 hover:bg-neutral-900/70",
          isLoading && "pointer-events-none opacity-60"
        )}
      >
        <input
          id="csv-upload"
          type="file"
          accept=".csv"
          onChange={handleFileInput}
          className="hidden"
          disabled={isLoading}
        />

        {/* Animated Flame Icon */}
        <motion.div
          animate={
            isDragging
              ? { scale: [1, 1.1, 1], rotate: [0, -5, 5, 0] }
              : isLoading
              ? { rotate: 360 }
              : {}
          }
          transition={
            isLoading
              ? { duration: 2, repeat: Infinity, ease: "linear" }
              : { duration: 0.5 }
          }
          className={cn(
            "w-24 h-24 rounded-3xl flex items-center justify-center mb-6 transition-all duration-300",
            isDragging
              ? "bg-gradient-to-br from-orange-500 to-red-600 shadow-2xl shadow-orange-500/40"
              : "bg-gradient-to-br from-neutral-800 to-neutral-900 border border-neutral-700"
          )}
        >
          <Flame
            className={cn(
              "w-12 h-12 transition-colors duration-300",
              isDragging ? "text-white" : "text-neutral-500"
            )}
          />
        </motion.div>

        {/* Text Content */}
        <div className="text-center space-y-2">
          <h3 className="text-xl font-bold text-white">
            {isLoading
              ? "Processing reviews..."
              : isDragging
              ? "Drop it like it's hot! 🔥"
              : "Upload your reviews CSV"}
          </h3>
          <p className="text-neutral-500 max-w-md">
            {isLoading
              ? "AI is clustering and analyzing your reviews"
              : "Drag & drop a CSV file here, or click to browse. We'll turn those brutal reviews into actionable tickets."}
          </p>
        </div>

        {/* File Format Hint */}
        {!isLoading && (
          <div className="mt-8 flex items-center gap-6 text-sm text-neutral-600">
            <div className="flex items-center gap-2">
              <FileSpreadsheet className="w-4 h-4" />
              <span>.csv format</span>
            </div>
            <div className="flex items-center gap-2">
              <Upload className="w-4 h-4" />
              <span>Max 10MB</span>
            </div>
          </div>
        )}

        {/* Loading Indicator */}
        {isLoading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="mt-8"
          >
            <div className="flex gap-1.5">
              {[0, 1, 2].map((i) => (
                <motion.div
                  key={i}
                  animate={{ y: [0, -8, 0] }}
                  transition={{
                    duration: 0.6,
                    repeat: Infinity,
                    delay: i * 0.15,
                  }}
                  className="w-3 h-3 rounded-full bg-gradient-to-r from-orange-500 to-red-600"
                />
              ))}
            </div>
          </motion.div>
        )}

        {/* Glow Effect on Drag */}
        {isDragging && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="absolute inset-0 rounded-3xl bg-gradient-to-br from-orange-500/10 via-transparent to-red-500/10 pointer-events-none"
          />
        )}
      </label>
    </motion.div>
  );
}

export default EmptyState;
