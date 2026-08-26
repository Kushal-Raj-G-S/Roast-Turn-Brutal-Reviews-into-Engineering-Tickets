"use client";

/**
 * PhoneMockup - Interactive Product Demo
 * =======================================
 * Scrolling the page = scrolling inside the app.
 * Modern, engaging experience with popping animations.
 * 
 * PHASES:
 * 1. Lock Screen (0.0 → 0.2) - Live time, realistic lock screen
 * 2. Opens Play Store (0.2 → 0.35) - Smooth unlock → Play Store
 * 3. Play Store Scrolls (0.35 → 1.0) - Reviews scroll with popping animations
 * 
 * Side content explains: Reviews → Engineering Tickets
 */

import { useRef, useState, useEffect, useMemo } from "react";
import { motion, useScroll, useTransform, useMotionValue, useSpring, useVelocity } from "framer-motion";

// ============================================================================
// PARTICLE FIELD - Subtle ambient depth
// ============================================================================

const PARTICLES = [
  { x: '10%', y: '20%', size: 2, duration: 8, delay: 0, opacity: 0.3, drift: 15 },
  { x: '85%', y: '15%', size: 2, duration: 10, delay: 1, opacity: 0.2, drift: -10 },
  { x: '25%', y: '70%', size: 2, duration: 9, delay: 2, opacity: 0.25, drift: 20 },
  { x: '70%', y: '60%', size: 2, duration: 11, delay: 0.5, opacity: 0.15, drift: -15 },
  { x: '45%', y: '85%', size: 2, duration: 7, delay: 1.5, opacity: 0.2, drift: 10 },
  { x: '15%', y: '40%', size: 2, duration: 12, delay: 3, opacity: 0.1, drift: -20 },
  { x: '90%', y: '75%', size: 2, duration: 8, delay: 2.5, opacity: 0.3, drift: 15 },
  { x: '55%', y: '25%', size: 2, duration: 10, delay: 1, opacity: 0.2, drift: -12 },
  { x: '35%', y: '55%', size: 2, duration: 9, delay: 0, opacity: 0.25, drift: 18 },
  { x: '80%', y: '35%', size: 2, duration: 11, delay: 2, opacity: 0.15, drift: -8 },
  { x: '20%', y: '90%', size: 2, duration: 7, delay: 1, opacity: 0.2, drift: 12 },
  { x: '60%', y: '10%', size: 2, duration: 10, delay: 0, opacity: 0.3, drift: -15 },
  { x: '40%', y: '65%', size: 2, duration: 8, delay: 2, opacity: 0.1, drift: 20 },
  { x: '75%', y: '45%', size: 2, duration: 12, delay: 1.5, opacity: 0.2, drift: -10 },
  { x: '30%', y: '30%', size: 2, duration: 9, delay: 3, opacity: 0.15, drift: 15 },
  { x: '65%', y: '80%', size: 2, duration: 11, delay: 0.5, opacity: 0.25, drift: -18 },
  { x: '50%', y: '50%', size: 2, duration: 7, delay: 2.5, opacity: 0.2, drift: 10 },
  { x: '95%', y: '55%', size: 2, duration: 10, delay: 1, opacity: 0.3, drift: -12 },
  { x: '5%', y: '75%', size: 2, duration: 8, delay: 0, opacity: 0.1, drift: 20 },
  { x: '48%', y: '95%', size: 2, duration: 9, delay: 2, opacity: 0.2, drift: -15 },
];

function ParticleField() {
  return (
    <>
      {PARTICLES.map((particle, i) => (
        <div
          key={i}
          className="particle"
          style={{
            position: 'absolute',
            left: particle.x,
            top: particle.y,
            width: `${particle.size}px`,
            height: `${particle.size}px`,
            background: `rgba(249, 115, 22, ${particle.opacity})`,
            borderRadius: '50%',
            pointerEvents: 'none',
            zIndex: 0,
            '--duration': `${particle.duration}s`,
            '--delay': `${particle.delay}s`,
            '--drift-x': `${particle.drift}px`,
          } as React.CSSProperties}
        />
      ))}
    </>
  );
}

// ============================================================================
// SCROLL PHASES
// ============================================================================
// Phase boundaries are computed at runtime (see buildPhases below) from the
// *actual* rendered height of the Play Store content, so the pinned scroll
// section always ends exactly when the content finishes revealing — no
// leftover "dead scroll" and nothing gets cut off if the content changes.

const LOCK_PX = 900; // scroll budget (px) for the lock-screen phase
const UNLOCK_PX = 500; // scroll budget (px) for the unlock → Play Store transition
const END_HOLD_PX = 250; // small pause once the final screen is fully revealed

function buildPhases(totalPx: number) {
  const lockEnd = LOCK_PX / totalPx;
  const unlockEnd = (LOCK_PX + UNLOCK_PX) / totalPx;
  return {
    LOCK_START: 0,
    LOCK_END: lockEnd,
    UNLOCK_START: lockEnd,
    UNLOCK_END: unlockEnd,
    SCROLL_START: unlockEnd,
    SCROLL_END: 1,
  } as const;
}

// ============================================================================
// PHONE DIMENSIONS
// ============================================================================

const PHONE = {
  WIDTH: 300,
  HEIGHT: 620,
  NOTCH_WIDTH: 80,
  NOTCH_HEIGHT: 24,
} as const;

// ============================================================================
// LOCK SCREEN with Live Time
// ============================================================================

function LockScreen() {
  const [time, setTime] = useState(new Date());
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const hours = time.getHours().toString().padStart(2, '0');
  const minutes = time.getMinutes().toString().padStart(2, '0');

  return (
    <div className="absolute inset-0 bg-gradient-to-b from-neutral-900 via-neutral-950 to-black flex flex-col items-center justify-center">
      {/* Time Display */}
      <div className="text-center mb-8">
        <motion.div 
          className="text-8xl font-bold text-white tracking-tight font-heading"
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.8, type: "spring", stiffness: 100 }}
          suppressHydrationWarning
        >
          {mounted ? `${hours}:${minutes}` : '12:00'}
        </motion.div>
        <motion.div 
          className="text-sm text-neutral-400 mt-3 font-mono tracking-wider"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3, duration: 0.6 }}
          suppressHydrationWarning
        >
          {mounted ? time.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' }) : 'Loading...'}
        </motion.div>
      </div>

      {/* Lock Icon */}
      <div className="mb-20">
        <svg className="w-8 h-8 text-neutral-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
        </svg>
      </div>

      {/* Swipe Up Hint */}
      <div className="absolute bottom-8 left-1/2 -translate-x-1/2">
        <div className="flex flex-col items-center">
          <svg className="w-6 h-6 text-neutral-600 animate-bounce" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
          </svg>
          <span className="text-[10px] text-neutral-600 mt-1">Swipe up</span>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// REVIEW DATA (More realistic, varied reviews)
// ============================================================================

const REVIEWS = [
  { 
    stars: 1, 
    text: "App crashes every single time I try to open it. Completely unusable since the last update. Wasted $50 on premium for nothing.",
    author: "angry_customer",
    time: "2 hours ago",
    helpful: 847,
    highlight: "crashes every single time",
    severity: "critical"
  },
  { 
    stars: 1, 
    text: "Lost ALL my data after updating. Years of work gone. No backup option. This is unacceptable for a paid app.",
    author: "data_disaster",
    time: "5 hours ago",
    helpful: 623,
    highlight: "Lost ALL my data",
    severity: "critical"
  },
  { 
    stars: 2, 
    text: "Battery drain is insane now. Phone goes from 100% to 20% in less than an hour with this app running. Please fix this!",
    author: "power_drain",
    time: "1 day ago",
    helpful: 412,
    highlight: "Battery drain is insane",
    severity: "high"
  },
  { 
    stars: 1, 
    text: "Login keeps failing over and over. Can't access my account. Support hasn't responded in 2 weeks. Moving to a competitor.",
    author: "locked_out_user",
    time: "2 days ago",
    helpful: 389,
    highlight: "Login keeps failing",
    severity: "critical"
  },
  { 
    stars: 2, 
    text: "Notifications completely broken. Missed important messages from clients. Cost me actual money. This is ridiculous.",
    author: "missed_alerts",
    time: "3 days ago",
    helpful: 256,
    highlight: "Notifications completely broken",
    severity: "high"
  },
  { 
    stars: 1, 
    text: "The new UI is a disaster. Can't find anything anymore. Who approved this redesign? Bring back the old version!",
    author: "confused_user",
    time: "4 days ago",
    helpful: 198,
    highlight: "new UI is a disaster",
    severity: "medium"
  },
  { 
    stars: 3, 
    text: "It works sometimes but crashes randomly. Support is slow to respond. Could be better with more polish.",
    author: "mediocre_exp",
    time: "5 days ago",
    helpful: 134,
    highlight: "crashes randomly",
    severity: "medium"
  },
  { 
    stars: 2, 
    text: "Sync between devices stopped working. Data shows differently on phone vs tablet. Very frustrating for work.",
    author: "sync_problems",
    time: "5 days ago",
    helpful: 167,
    highlight: "Sync between devices stopped",
    severity: "high"
  },
  { 
    stars: 1, 
    text: "App freezes for 10+ seconds whenever I try to upload anything. Makes it completely unusable for work. Need urgent fix.",
    author: "frozen_app",
    time: "1 week ago",
    helpful: 145,
    highlight: "freezes for 10+ seconds",
    severity: "critical"
  },
  { 
    stars: 2, 
    text: "Too many bugs. Features half-work. Feels like a beta release, not a finished product. Disappointed.",
    author: "beta_tester",
    time: "1 week ago",
    helpful: 98,
    highlight: "Too many bugs",
    severity: "high"
  },
];

// ============================================================================
// COMPONENT: ANIMATED REVIEW CARD with Modern Pop Effect
// ============================================================================

function ReviewCard({ review, scrollProgress }: { review: typeof REVIEWS[0]; scrollProgress: number }) {
  // Highlight the key phrase
  const highlightText = (text: string, highlight: string) => {
    const parts = text.split(new RegExp(`(${highlight})`, 'gi'));
    return parts.map((part, i) => 
      part.toLowerCase() === highlight.toLowerCase() 
        ? <span key={i} className="text-red-400 font-semibold">{part}</span>
        : part
    );
  };

  const severityColors: Record<string, string> = {
    critical: 'bg-red-500/20 text-red-400 border-red-500/30',
    high: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    low: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.8, y: 40, rotateX: -15 }}
      animate={{ opacity: 1, scale: 1, y: 0, rotateX: 0 }}
      transition={{
        type: "spring",
        stiffness: 200,
        damping: 15,
        delay: Math.random() * 0.3
      }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: false, amount: 0.3 }}
      whileHover={{ scale: 1.02, transition: { duration: 0.2 } }}
      className="bg-gradient-to-br from-neutral-800/80 to-neutral-900/80 backdrop-blur-sm rounded-xl p-3 mb-2 border border-neutral-700/30 shadow-lg"
    >
      {/* Header with animated stars */}
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-1">
          {[1,2,3,4,5].map(i => (
            <motion.svg
              key={i}
              initial={{ scale: 0, rotate: -360 }}
              animate={{ scale: 1, rotate: 0 }}
              transition={{ delay: 0.3 + i * 0.08, duration: 0.8, type: "spring", stiffness: 150, damping: 10 }}
              whileHover={{ scale: 1.3, rotate: 15, transition: { duration: 0.2 } }}
              className={`w-2.5 h-2.5 ${i <= review.stars ? 'text-yellow-500' : 'text-neutral-700'}`} 
              fill="currentColor" 
              viewBox="0 0 20 20"
            >
              <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/>
            </motion.svg>
          ))}
        </div>
        <motion.span 
          initial={{ opacity: 0, x: 10 }}
          animate={{ opacity: 1, x: 0 }}
          className="text-[8px] text-neutral-500"
        >
          {review.time}
        </motion.span>
      </div>
      
      {/* Severity Badge */}
      <motion.div
        initial={{ scale: 0, x: -20, rotate: -12 }}
        animate={{ scale: 1, x: 0, rotate: 0 }}
        transition={{ delay: 0.5, duration: 0.6, type: "spring", stiffness: 180, damping: 12 }}
        whileHover={{ scale: 1.1, rotate: 3, transition: { duration: 0.2 } }}
        className={`inline-block px-2 py-0.5 rounded-full text-[7px] font-black uppercase tracking-widest mb-1.5 border font-display ${severityColors[review.severity]} ${
          review.severity === 'critical' ? 'badge-critical' : 
          review.severity === 'high' ? 'badge-high' : 
          review.severity === 'medium' ? 'badge-medium' : ''
        }`}
      >
        {review.severity}
      </motion.div>

      {/* Review Text with stagger effect */}
      <motion.p 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2 }}
        className="text-[10px] text-neutral-300 leading-relaxed mb-1.5 font-sans"
      >
        {highlightText(review.text, review.highlight)}
      </motion.p>
      
      {/* Footer */}
      <div className="flex items-center justify-between pt-1.5 border-t border-neutral-700/30">
        <motion.span 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="text-[8px] text-neutral-500"
        >
          @{review.author}
        </motion.span>
        <motion.div 
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.35, type: "spring" }}
          className="flex items-center gap-1 text-[8px] text-neutral-500"
        >
          <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" />
          </svg>
          <span>{review.helpful}</span>
        </motion.div>
      </div>
    </motion.div>
  );
}

// ============================================================================
// SCREEN: PLAY STORE (Scrollable content with random app)
// ============================================================================

function PlayStoreContent({ scrollY, scrollProgress }: { scrollY: number; scrollProgress: number }) {
  return (
    <div
      className="flex flex-col bg-[#0a0a0a] p-4 pt-8"
    >
      {/* Status Bar */}
      <div className="flex items-center justify-between text-[9px] text-white mb-3">
        <motion.span
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="font-semibold tabular-nums"
        >
          9:41
        </motion.span>
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.1 }}
          className="flex items-center gap-1.5"
        >
          {/* Cellular signal — 4 ascending bars */}
          <svg width="16" height="11" viewBox="0 0 16 11" fill="none" aria-hidden>
            <rect x="0" y="7" width="3" height="4" rx="0.6" fill="currentColor" />
            <rect x="4.3" y="5" width="3" height="6" rx="0.6" fill="currentColor" />
            <rect x="8.6" y="3" width="3" height="8" rx="0.6" fill="currentColor" />
            <rect x="13" y="0" width="3" height="11" rx="0.6" fill="currentColor" />
          </svg>

          {/* Wi-Fi */}
          <svg width="14" height="11" viewBox="0 0 14 11" fill="none" aria-hidden>
            <path
              d="M7 9.3a1.1 1.1 0 100 2.2 1.1 1.1 0 000-2.2z"
              fill="currentColor"
            />
            <path
              d="M3.6 6.7a5 5 0 016.8 0"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
              fill="none"
            />
            <path
              d="M1 3.9a9 9 0 0112 0"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
              fill="none"
              opacity="0.9"
            />
          </svg>

          {/* Battery */}
          <div className="flex items-center">
            <div className="w-5 h-2.5 border border-white/70 rounded-[3px] relative p-[1px]">
              <div className="h-full bg-white rounded-[1px]" style={{ width: '82%' }} />
            </div>
            <div className="w-[1.5px] h-1 bg-white/70 rounded-r-sm ml-[1px]" />
          </div>
        </motion.div>
      </div>

      {/* App Header - Random App "FitTracker Pro" */}
      <motion.div 
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3, type: "spring", stiffness: 180, damping: 15 }}
        className="flex items-start gap-3 mb-3"
      >
        <motion.div 
          initial={{ scale: 0, rotate: -360 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ delay: 0.5, duration: 1.0, type: "spring", stiffness: 150, damping: 12 }}
          whileHover={{ scale: 1.1, rotate: 10, transition: { duration: 0.3 } }}
          className="w-14 h-14 rounded-2xl bg-gradient-to-br from-purple-500 via-pink-500 to-orange-500 flex items-center justify-center shrink-0 shadow-lg shadow-purple-500/30"
        >
          <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </motion.div>
        <div className="flex-1 min-w-0">
          <motion.h2 
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.4 }}
            className="text-sm font-black text-white font-heading tracking-tight"
          >
            FitTracker Pro
          </motion.h2>
          <motion.p 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.45 }}
            className="text-[9px] text-neutral-500 font-mono"
          >
            HealthTech Inc.
          </motion.p>
          <div className="flex items-center gap-1.5 mt-1">
            <div className="flex">
              {[1,2].map(i => (
                <motion.svg
                  key={i}
                  initial={{ scale: 0, rotate: -180 }}
                  animate={{ scale: 1, rotate: 0 }}
                  transition={{ delay: 0.5 + i * 0.05, type: "spring" }}
                  className="w-2.5 h-2.5 text-yellow-500" 
                  fill="currentColor" 
                  viewBox="0 0 20 20"
                >
                  <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/>
                </motion.svg>
              ))}
              {[1,2,3].map(i => (
                <motion.svg
                  key={`empty-${i}`}
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ delay: 0.6 + i * 0.05, type: "spring" }}
                  className="w-2.5 h-2.5 text-neutral-600" 
                  fill="currentColor" 
                  viewBox="0 0 20 20"
                >
                  <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/>
                </motion.svg>
              ))}
            </div>
            <motion.span 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.75 }}
              className="text-[8px] text-neutral-500"
            >
              2.1 · 52K reviews
            </motion.span>
          </div>
        </div>
      </motion.div>

      {/* Install Button */}
      <motion.button 
        initial={{ opacity: 0, scale: 0.8, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        whileHover={{ scale: 1.05, boxShadow: "0 0 25px rgba(16, 185, 129, 0.5)" }}
        whileTap={{ scale: 0.95 }}
        transition={{ delay: 1.0, duration: 0.6, type: "spring", stiffness: 180, damping: 12 }}
        className="w-full py-2 bg-gradient-to-r from-emerald-600 to-emerald-500 rounded-lg text-white text-[10px] font-black mb-3 shadow-lg shadow-emerald-500/20 font-display tracking-wider"
      >
        Install
      </motion.button>

      {/* Quick Stats */}
      <motion.div 
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.9 }}
        className="flex items-center justify-around py-2 border-y border-neutral-800/50 mb-3"
      >
        <div className="text-center">
          <p className="text-[10px] font-semibold text-white">2.1★</p>
          <p className="text-[7px] text-neutral-500">52K reviews</p>
        </div>
        <div className="w-px h-6 bg-neutral-800" />
        <div className="text-center">
          <p className="text-[10px] font-semibold text-white">10M+</p>
          <p className="text-[7px] text-neutral-500">Downloads</p>
        </div>
        <div className="w-px h-6 bg-neutral-800" />
        <div className="text-center">
          <p className="text-[10px] font-semibold text-white">E</p>
          <p className="text-[7px] text-neutral-500">Everyone</p>
        </div>
      </motion.div>

      {/* Ratings Breakdown */}
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.0 }}
        className="mb-4"
      >
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-semibold text-white">Ratings and reviews</h3>
        </div>
        
        {/* Rating Bars */}
        <div className="flex items-start gap-3">
          <div className="text-center">
            <motion.p 
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ delay: 1.1, type: "spring" }}
              className="text-3xl font-bold text-white"
            >
              2.1
            </motion.p>
            <div className="flex justify-center my-1">
              {[1,2].map(i => (
                <motion.svg
                  key={i}
                  initial={{ scale: 0, rotate: -180 }}
                  animate={{ scale: 1, rotate: 0 }}
                  transition={{ delay: 1.2 + i * 0.05 }}
                  className="w-2 h-2 text-yellow-500" 
                  fill="currentColor" 
                  viewBox="0 0 20 20"
                >
                  <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/>
                </motion.svg>
              ))}
              {[1,2,3].map(i => (
                <svg key={`empty-${i}`} className="w-2 h-2 text-neutral-600" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/>
                </svg>
              ))}
            </div>
            <p className="text-[7px] text-neutral-500">52,847</p>
          </div>
          <div className="flex-1 space-y-1">
            {[
              { stars: 5, percent: 5 },
              { stars: 4, percent: 8 },
              { stars: 3, percent: 12 },
              { stars: 2, percent: 28 },
              { stars: 1, percent: 47 },
            ].map(({ stars, percent }, i) => (
              <motion.div 
                key={stars} 
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 1.3 + i * 0.05 }}
                className="flex items-center gap-1.5"
              >
                <span className="text-[8px] text-neutral-500 w-2">{stars}</span>
                <div className="flex-1 h-1.5 bg-neutral-800 rounded-full overflow-hidden">
                  <motion.div 
                    initial={{ width: 0 }}
                    animate={{ width: `${percent}%` }}
                    transition={{ delay: 1.4 + i * 0.05, duration: 0.5 }}
                    className={`h-full rounded-full ${stars <= 2 ? 'bg-gradient-to-r from-red-500 to-orange-500' : 'bg-gradient-to-r from-emerald-500 to-green-400'}`}
                  />
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </motion.div>

      {/* Reviews Section Header */}
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.6 }}
        className="mb-2"
      >
        <div className="flex items-center gap-2 mb-3">
          <button className="px-2 py-1 bg-neutral-800 rounded-full text-[8px] text-neutral-400">Most relevant</button>
          <motion.button 
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: 1.7, type: "spring" }}
            className="px-2 py-1 bg-gradient-to-r from-red-500/30 to-orange-500/30 border border-red-500/30 rounded-full text-[8px] text-red-400 font-medium"
          >
            🔥 Critical Issues
          </motion.button>
        </div>
      </motion.div>

      {/* Review Cards with staggered pop-in */}
      {REVIEWS.map((review, i) => (
        <ReviewCard key={i} review={review} scrollProgress={scrollProgress} />
      ))}

      {/* Spacer */}
      <div className="h-16" />

      {/* AI PROCESSING TERMINAL CARD - with ROAST branding */}
      <div 
        className="my-8 w-full h-[500px] flex flex-col items-center justify-center gap-4 p-8 rounded-2xl" 
        style={{ 
          background: "#000",
          isolation: "isolate",
          zIndex: 20,
          border: '1px solid rgba(249, 115, 22, 0.1)'
        }}
      >
        <div className="text-center w-full">
          {/* Using ROAST with Logo */}
          <div className="flex flex-col items-center gap-3 mb-8">
            <motion.img
              src="/logo.png"
              alt="ROAST Logo"
              initial={{ scale: 0.8, opacity: 0 }}
              whileInView={{ scale: 1, opacity: 1 }}
              viewport={{ once: false }}
              transition={{ duration: 0.4 }}
              className="w-12 h-12"
            />
            <p className="text-white/50 text-xs uppercase tracking-widest font-mono">
              using ROAST
            </p>
          </div>
          
          <p className="text-white/30 text-xs uppercase tracking-widest mb-6 font-mono">
            processing reviews...
          </p>
          
          <p className="text-white font-mono text-sm mt-6 opacity-60">
            Clustering 52,847 reviews...
          </p>
          <p className="text-white font-mono text-sm mt-2 opacity-60">
            Detecting severity patterns...
          </p>
          <p className="text-white font-mono text-sm mt-2 opacity-60">
            Generating engineering tickets...
          </p>
          
          <div className="mt-8 flex justify-center gap-1">
            {[1, 2, 3, 4, 5].map(i => (
              <div 
                key={i} 
                className="w-1.5 h-1.5 rounded-full bg-orange-500 animate-pulse" 
                style={{ animationDelay: `${i * 0.15}s`, opacity: 0.4 }} 
              />
            ))}
          </div>
        </div>
      </div>

      {/* Spacer */}
      <div className="h-16" />

      {/* SPONGEBOB MEME IMAGE */}
      <motion.img
        src="/meme.jpg"
        alt="A Few Moments Later"
        initial={{ opacity: 0, scale: 0.95 }}
        whileInView={{ opacity: 1, scale: 1 }}
        viewport={{ once: false, amount: 0.3 }}
        transition={{ duration: 0.6, type: "spring" }}
        className="my-8 w-full h-auto rounded-2xl"
        style={{ 
          isolation: "isolate",
          objectFit: "cover",
          maxHeight: "400px"
        }}
      />

      {/* Spacer */}
      <div className="h-16" />

      {/* EXACT SAME STRUCTURE AS 2.1 BUT NOW WITH 4.8 STARS */}
      <motion.div
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: false, amount: 0.2 }}
        transition={{ duration: 0.4 }}
        className="mb-6"
      >
        {/* App Header - SAME STRUCTURE, 4.8 STARS */}
        <motion.div 
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: false }}
          transition={{ duration: 0.3 }}
          className="flex gap-3 mb-4"
        >
          <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shrink-0">
            <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-bold text-white mb-0.5 truncate">FitTracker Pro</h2>
            <p className="text-[9px] text-neutral-500 mb-1">HealthTech Inc.</p>
            <div className="flex items-center gap-2 mb-1">
              <div className="flex">
                {[1,2,3,4,5].map(i => (
                  <svg
                    key={i}
                    className="w-2.5 h-2.5 text-yellow-500"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                  >
                    <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/>
                  </svg>
                ))}
              </div>
              <span className="text-[9px] text-emerald-400 font-bold">4.8 · 52K reviews</span>
            </div>
          </div>
        </motion.div>

        {/* Quick Stats - SAME STRUCTURE */}
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: false }}
          transition={{ duration: 0.3 }}
          className="flex items-center gap-6 mb-4 pb-4 border-b border-neutral-800"
        >
          <div className="flex items-center gap-2">
            <svg className="w-3 h-3 text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
              <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/>
            </svg>
            <span className="text-[9px] text-neutral-400">4.8★</span>
          </div>
          <div className="w-px h-6 bg-neutral-800" />
          <div className="text-center">
            <p className="text-[10px] font-semibold text-white">10M+</p>
            <p className="text-[7px] text-neutral-500">Downloads</p>
          </div>
          <div className="w-px h-6 bg-neutral-800" />
          <div className="text-center">
            <p className="text-[10px] font-semibold text-white">E</p>
            <p className="text-[7px] text-neutral-500">Everyone</p>
          </div>
        </motion.div>

        {/* Ratings Breakdown - SAME STRUCTURE */}
        <motion.div 
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: false }}
          transition={{ duration: 0.3 }}
          className="mb-4"
        >
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold text-white">Ratings and reviews</h3>
          </div>
          
          <div className="flex items-start gap-3">
            <div className="text-center">
              <p className="text-3xl font-bold text-emerald-400">4.8</p>
              <div className="flex justify-center my-1">
                {[1,2,3,4,5].map(i => (
                  <svg
                    key={i}
                    className="w-2 h-2 text-yellow-500" 
                    fill="currentColor" 
                    viewBox="0 0 20 20"
                  >
                    <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/>
                  </svg>
                ))}
              </div>
              <p className="text-[7px] text-neutral-500">52,847</p>
            </div>
            <div className="flex-1 space-y-1">
              {[
                { stars: 5, percent: 78 },
                { stars: 4, percent: 15 },
                { stars: 3, percent: 5 },
                { stars: 2, percent: 1 },
                { stars: 1, percent: 1 },
              ].map(({ stars, percent }) => (
                <div key={stars} className="flex items-center gap-1.5">
                  <span className="text-[8px] text-neutral-500 w-2">{stars}</span>
                  <div className="flex-1 h-1.5 bg-neutral-800 rounded-full overflow-hidden">
                    <div 
                      className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-green-400"
                      style={{ width: `${percent}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* Reviews Section Header - SAME STRUCTURE */}
        <motion.div 
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: false }}
          transition={{ duration: 0.3 }}
          className="mb-2"
        >
          <div className="flex items-center gap-2 mb-3">
            <button className="px-2 py-1 bg-neutral-800 rounded-full text-[8px] text-neutral-400">Most relevant</button>
            <button className="px-2 py-1 bg-gradient-to-r from-emerald-500/30 to-green-500/30 border border-emerald-500/30 rounded-full text-[8px] text-emerald-400 font-medium">
              ✓ All Issues Fixed
            </button>
          </div>
        </motion.div>

        {/* SAME REVIEWERS - NOW WITH 5 STARS */}
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: false }}
          transition={{ duration: 0.3 }}
          className="space-y-3"
        >
          <div className="flex items-center justify-between mb-3">
            <p className="text-[10px] text-neutral-400">Most helpful</p>
            <div className="px-2 py-1 bg-emerald-500/20 rounded-full text-[7px] text-emerald-400 font-bold">
              ALL ISSUES FIXED ✓
            </div>
          </div>
          
          {/* Review 1 - @power_drainer NOW HAPPY */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: false }}
            transition={{ delay: 0.7 }}
            className="p-3 bg-gradient-to-br from-emerald-500/5 to-green-500/5 rounded-xl border border-emerald-500/20"
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex">
                {[1,2,3,4,5].map(i => (
                  <svg key={i} className="w-2 h-2 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/>
                  </svg>
                ))}
              </div>
              <span className="text-[8px] text-neutral-500">Updated review</span>
            </div>
            <div className="mb-2">
              <span className="px-2 py-0.5 rounded-full text-[7px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                RESOLVED
              </span>
            </div>
            <p className="text-[10px] text-neutral-300 leading-relaxed mb-2">
              <strong className="text-emerald-400">OMG they actually fixed it! 🎉</strong> Battery drain is completely gone. 
              App runs smoothly in background now. Can't believe they listened!
            </p>
            <div className="flex items-center justify-between pt-2 border-t border-neutral-800">
              <span className="text-[8px] text-neutral-500">@power_drainer</span>
              <div className="flex items-center gap-1 text-[8px] text-emerald-400">
                <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" />
                </svg>
                <span>523</span>
              </div>
            </div>
          </motion.div>

          {/* Review 2 - @locked_out_user NOW HAPPY */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: false }}
            transition={{ delay: 0.8 }}
            className="p-3 bg-gradient-to-br from-emerald-500/5 to-green-500/5 rounded-xl border border-emerald-500/20"
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex">
                {[1,2,3,4,5].map(i => (
                  <svg key={i} className="w-2 h-2 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/>
                  </svg>
                ))}
              </div>
              <span className="text-[8px] text-neutral-500">Updated review</span>
            </div>
            <div className="mb-2">
              <span className="px-2 py-0.5 rounded-full text-[7px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                RESOLVED
              </span>
            </div>
            <p className="text-[10px] text-neutral-300 leading-relaxed mb-2">
              <strong className="text-emerald-400">Support team is incredible!</strong> They responded within 2 weeks, 
              fixed the login issue, and now I have access to everything. Moving back from competitor!
            </p>
            <div className="flex items-center justify-between pt-2 border-t border-neutral-800">
              <span className="text-[8px] text-neutral-500">@locked_out_user</span>
              <div className="flex items-center gap-1 text-[8px] text-emerald-400">
                <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" />
                </svg>
                <span>412</span>
              </div>
            </div>
          </motion.div>

          {/* Review 3 - @missed_alerts NOW HAPPY */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: false }}
            transition={{ delay: 0.9 }}
            className="p-3 bg-gradient-to-br from-emerald-500/5 to-green-500/5 rounded-xl border border-emerald-500/20"
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex">
                {[1,2,3,4,5].map(i => (
                  <svg key={i} className="w-2 h-2 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/>
                  </svg>
                ))}
              </div>
              <span className="text-[8px] text-neutral-500">Updated review</span>
            </div>
            <div className="mb-2">
              <span className="px-2 py-0.5 rounded-full text-[7px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                RESOLVED
              </span>
            </div>
            <p className="text-[10px] text-neutral-300 leading-relaxed mb-2">
              <strong className="text-emerald-400">Notifications work perfectly now!</strong> Getting all my important 
              alerts. No more missed messages. This saved my business relationship!
            </p>
            <div className="flex items-center justify-between pt-2 border-t border-neutral-800">
              <span className="text-[8px] text-neutral-500">@missed_alerts</span>
              <div className="flex items-center gap-1 text-[8px] text-emerald-400">
                <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" />
                </svg>
                <span>389</span>
              </div>
            </div>
          </motion.div>

          {/* Review 4 - @roast_age NOW HAPPY */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: false }}
            transition={{ delay: 1.0 }}
            className="p-3 bg-gradient-to-br from-emerald-500/5 to-green-500/5 rounded-xl border border-emerald-500/20"
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex">
                {[1,2,3,4,5].map(i => (
                  <svg key={i} className="w-2 h-2 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/>
                  </svg>
                ))}
              </div>
              <span className="text-[8px] text-neutral-500">Updated review</span>
            </div>
            <div className="mb-2">
              <span className="px-2 py-0.5 rounded-full text-[7px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                RESOLVED
              </span>
            </div>
            <p className="text-[10px] text-neutral-300 leading-relaxed mb-2">
              <strong className="text-emerald-400">The upload freeze is finally fixed!</strong> Can upload anything now 
              without crashes. Whatever they did in the backend, it works beautifully!
            </p>
            <div className="flex items-center justify-between pt-2 border-t border-neutral-800">
              <span className="text-[8px] text-neutral-500">@roast_age</span>
              <div className="flex items-center gap-1 text-[8px] text-emerald-400">
                <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" />
                </svg>
                <span>148</span>
              </div>
            </div>
          </motion.div>
        </motion.div>
      </motion.div>

      {/* Bottom padding */}
      <div className="h-32" />
    </div>
  );
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

// Height of the phone's visible screen area — matches the CSS
// `calc(100% - 40px)` applied to the screen container below.
const PHONE_SCREEN_HEIGHT = PHONE.HEIGHT - 40;
const FALLBACK_CONTENT_HEIGHT = 4300; // used until the real content is measured

export function PhoneMockup() {
  const containerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [isScrolling, setIsScrolling] = useState(false);
  const scrollTimeout = useRef<NodeJS.Timeout | null>(null);
  const [contentHeight, setContentHeight] = useState(FALLBACK_CONTENT_HEIGHT);
  const [viewportHeight, setViewportHeight] = useState(900);

  // Measure the actual rendered height of the scrolling Play Store content so
  // the pinned section's scroll length always matches exactly — no dead
  // scroll space, nothing cut off at the bottom, regardless of how much
  // content (reviews, cards, images) is in there.
  useEffect(() => {
    if (!contentRef.current) return;
    const measure = () => {
      const h = contentRef.current?.scrollHeight;
      if (h && h > 0) setContentHeight(h);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(contentRef.current);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const updateViewport = () => setViewportHeight(window.innerHeight);
    updateViewport();
    window.addEventListener('resize', updateViewport);
    return () => window.removeEventListener('resize', updateViewport);
  }, []);

  const SCROLL_DISTANCE = Math.max(contentHeight - PHONE_SCREEN_HEIGHT, 400);
  const TOTAL_SCROLL_PX = LOCK_PX + UNLOCK_PX + SCROLL_DISTANCE + END_HOLD_PX;
  const PHASE = useMemo(() => buildPhases(TOTAL_SCROLL_PX), [TOTAL_SCROLL_PX]);
  const sectionHeight = TOTAL_SCROLL_PX + viewportHeight;

  const { scrollYProgress: rawScrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start start", "end end"],
  });

  // Spring-smooth the raw scroll progress so the whole sequence feels like a
  // physical, weighted motion instead of snapping 1:1 with wheel/touch deltas.
  const scrollYProgress = useSpring(rawScrollYProgress, {
    stiffness: 300,
    damping: 40,
    mass: 0.4,
  });

  // ==========================================================================
  // PREMIUM INTERACTION 1: Scroll-velocity motion blur
  // Fast scrolling blurs the phone slightly, like a camera whip-pan; it
  // sharpens back up the moment scrolling settles. This is the signature
  // "weighted" feel of high-end scrollytelling sites.
  // ==========================================================================
  const scrollVelocity = useVelocity(scrollYProgress);
  const smoothVelocity = useSpring(scrollVelocity, { stiffness: 300, damping: 40 });
  const scrollBlur = useTransform(smoothVelocity, (v) => {
    const px = Math.min(Math.abs(v) * 6, 7);
    return `blur(${px.toFixed(2)}px)`;
  });

  // ==========================================================================
  // PREMIUM INTERACTION 2: Cursor-reactive 3D tilt
  // The phone subtly tilts toward the pointer, like it's a physical object
  // sitting under a light source — a common Apple-style product-page touch.
  // ==========================================================================
  const pointerX = useMotionValue(0);
  const pointerY = useMotionValue(0);
  const tiltRotateX = useSpring(useTransform(pointerY, [-0.5, 0.5], [10, -10]), {
    stiffness: 150,
    damping: 20,
    mass: 0.5,
  });
  const tiltRotateY = useSpring(useTransform(pointerX, [-0.5, 0.5], [-10, 10]), {
    stiffness: 150,
    damping: 20,
    mass: 0.5,
  });

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    pointerX.set((e.clientX - rect.left) / rect.width - 0.5);
    pointerY.set((e.clientY - rect.top) / rect.height - 0.5);
  };
  const handlePointerLeave = () => {
    pointerX.set(0);
    pointerY.set(0);
  };

  // Track scrolling state to pause floating animation
  useEffect(() => {
    const handleScroll = () => {
      setIsScrolling(true);
      if (scrollTimeout.current) {
        clearTimeout(scrollTimeout.current);
      }
      scrollTimeout.current = setTimeout(() => {
        setIsScrolling(false);
      }, 500);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', handleScroll);
      if (scrollTimeout.current) {
        clearTimeout(scrollTimeout.current);
      }
    };
  }, []);

  // ==========================================================================
  // PHONE SHELL (Minimal, stable)
  // ==========================================================================

  const phoneScale = useTransform(
    scrollYProgress,
    [PHASE.LOCK_START, PHASE.UNLOCK_END],
    [0.95, 1.0]
  );

  const phoneBorderRadius = useTransform(
    scrollYProgress,
    [PHASE.LOCK_START, PHASE.UNLOCK_END],
    [40, 32]
  );

  const phoneShadow = useTransform(
    scrollYProgress,
    [0, 0.5],
    [
      "0 25px 50px -15px rgba(0,0,0,0.5)",
      "0 30px 60px -15px rgba(0,0,0,0.6)"
    ]
  );

  // ==========================================================================
  // PHASE 1: LOCK SCREEN
  // ==========================================================================

  const lockOpacity = useTransform(
    scrollYProgress,
    [PHASE.LOCK_START, PHASE.LOCK_END - 0.05, PHASE.LOCK_END],
    [1, 1, 0]
  );

  // Swipe-up-to-unlock: the whole lock screen slides upward and defocuses,
  // like it's being physically swiped away, instead of just fading out.
  const lockY = useTransform(
    scrollYProgress,
    [PHASE.LOCK_END - 0.12, PHASE.LOCK_END],
    [0, -140]
  );

  const lockScale = useTransform(
    scrollYProgress,
    [PHASE.LOCK_END - 0.1, PHASE.LOCK_END],
    [1, 1.06]
  );

  const lockBlurPx = useTransform(
    scrollYProgress,
    [PHASE.LOCK_END - 0.1, PHASE.LOCK_END],
    [0, 6]
  );
  const lockFilter = useTransform(lockBlurPx, (v) => `blur(${v.toFixed(1)}px)`);

  // ==========================================================================
  // PHASE 2: UNLOCK → PLAY STORE
  // ==========================================================================

  const storeOpacity = useTransform(
    scrollYProgress,
    [PHASE.UNLOCK_START, PHASE.UNLOCK_END],
    [0, 1]
  );

  const storeScale = useTransform(
    scrollYProgress,
    [PHASE.UNLOCK_START, PHASE.UNLOCK_END],
    [0.95, 1.0]
  );

  // ==========================================================================
  // PHASE 3: PLAY STORE SCROLLS — distance is derived from the measured
  // content height above, so it always lines up with SCROLL_END exactly.
  // ==========================================================================

  const storeScrollY = useTransform(
    scrollYProgress,
    [PHASE.SCROLL_START, PHASE.SCROLL_END],
    [0, -SCROLL_DISTANCE]
  );

  // ==========================================================================
  // SIDE ANNOTATIONS (Progressive reveal)
  // ==========================================================================

  const leftAnnotation1Opacity = useTransform(scrollYProgress, [0.4, 0.45], [0, 1]);
  const leftAnnotation2Opacity = useTransform(scrollYProgress, [0.55, 0.6], [0, 1]);
  const leftAnnotation3Opacity = useTransform(scrollYProgress, [0.7, 0.75], [0, 1]);

  const rightAnnotation1Opacity = useTransform(scrollYProgress, [0.5, 0.55], [0, 1]);
  const rightAnnotation2Opacity = useTransform(scrollYProgress, [0.65, 0.7], [0, 1]);
  const rightAnnotation3Opacity = useTransform(scrollYProgress, [0.8, 0.85], [0, 1]);

  // ==========================================================================
  // SCREEN GLOW - Reactive to scroll phase
  // ==========================================================================
  
  // Determine if we're in critical (red) or resolved (green) phase
  const currentProgress = scrollYProgress.get();
  const isInCriticalPhase = currentProgress >= 0.4 && currentProgress < 0.75;
  const isInResolvedPhase = currentProgress >= 0.85;

  // ==========================================================================
  // RENDER
  // ==========================================================================

  return (
    <section
      ref={containerRef}
      className="relative"
      style={{ height: `${sectionHeight}px` }}
    >
      {/* Sticky Container - Below Navbar */}
      <div
        className="sticky top-20 h-[calc(100vh-5rem)] flex items-center justify-center overflow-hidden px-4"
        style={{ perspective: 1400 }}
        onPointerMove={handlePointerMove}
        onPointerLeave={handlePointerLeave}
      >

        {/* ================================================================ */}
        {/* LAYERED DEPTH BACKGROUND */}
        {/* ================================================================ */}
        <div className="absolute inset-0 bg-black" />
        
        {/* Animated Orb 1 - Bottom Left */}
        <div 
          className="absolute pointer-events-none z-0"
          style={{
            left: '-200px',
            bottom: '-100px',
            width: '800px',
            height: '600px',
            background: 'radial-gradient(circle, rgba(249, 115, 22, 0.06) 0%, transparent 70%)',
            filter: 'blur(120px)',
            animation: 'orbDrift1 18s ease-in-out infinite alternate',
          }}
        />
        
        {/* Animated Orb 2 - Top Right */}
        <div 
          className="absolute pointer-events-none z-0"
          style={{
            right: '-150px',
            top: '0',
            width: '600px',
            height: '600px',
            background: 'radial-gradient(circle, rgba(220, 38, 38, 0.04) 0%, transparent 70%)',
            filter: 'blur(100px)',
            animation: 'orbDrift2 22s ease-in-out infinite alternate',
          }}
        />
        
        {/* Animated Orb 3 - Center Top */}
        <div 
          className="absolute pointer-events-none z-0"
          style={{
            left: '50%',
            top: '0',
            transform: 'translateX(-50%)',
            width: '400px',
            height: '200px',
            background: 'radial-gradient(ellipse, rgba(249, 115, 22, 0.03) 0%, transparent 70%)',
            filter: 'blur(80px)',
          }}
        />

        {/* Particle Field */}
        <ParticleField />

        {/* ================================================================ */}
        {/* PHONE SHELL - PREMIUM CSS FRAME */}
        {/* ================================================================ */}
        {/* Outer wrapper owns the idle CSS float bob — kept on its own element
            because a running CSS animation on `transform` overrides any
            inline/Framer `transform` set on that same element. */}
        <div className={`relative z-10 phone-float ${isScrolling ? 'phone-float-paused' : ''}`}>
        <motion.div
          style={{
            width: PHONE.WIDTH,
            height: PHONE.HEIGHT,
            scale: phoneScale,
            rotateX: tiltRotateX,
            rotateY: tiltRotateY,
            filter: scrollBlur,
            transformStyle: "preserve-3d",
            willChange: "transform, filter",
            isolation: "isolate",
          }}
        >
          {/* Phone Frame Wrapper - THE visible phone shell */}
          <div
            style={{
              position: 'relative',
              width: '100%',
              height: '100%',
              borderRadius: '44px',
              background: 'linear-gradient(145deg, #1a1a1a 0%, #0d0d0d 100%)',
              boxShadow: `
                0 0 0 1px rgba(255,255,255,0.08),
                0 0 0 2px rgba(0,0,0,0.8),
                0 0 0 3px rgba(255,255,255,0.04),
                0 50px 100px rgba(0,0,0,0.9),
                0 0 80px rgba(249,115,22,0.06)
              `,
              padding: '12px',
            }}
          >
            {/* Dynamic Island */}
            <div style={{
              position: 'absolute',
              top: '16px',
              left: '50%',
              transform: 'translateX(-50%)',
              width: '104px',
              height: '30px',
              background: 'linear-gradient(180deg, #050505 0%, #000 100%)',
              borderRadius: '999px',
              zIndex: 10,
              boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.05), inset 0 1px 2px rgba(255,255,255,0.04), 0 2px 6px rgba(0,0,0,0.6)'
            }}>
              {/* Camera Lens */}
              <div style={{
                position: 'absolute',
                right: '9px',
                top: '50%',
                transform: 'translateY(-50%)',
                width: '9px',
                height: '9px',
                borderRadius: '50%',
                background: 'radial-gradient(circle at 35% 35%, #2a3a5e, #0a0e1a 70%)',
                boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.1), 0 0 4px rgba(100,150,255,0.25)'
              }} />
              {/* Sensor dot */}
              <div style={{
                position: 'absolute',
                right: '26px',
                top: '50%',
                transform: 'translateY(-50%)',
                width: '4px',
                height: '4px',
                borderRadius: '50%',
                background: '#111',
                boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.06)'
              }} />
            </div>

            {/* Screen Area - Content Container */}
            <div style={{
              borderRadius: '32px',
              overflow: 'hidden',
              background: '#000',
              position: 'relative',
              height: 'calc(100% - 40px)',
            }}>
              {/* Glass Sheen at top of screen */}
              <div style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                height: '35%',
                zIndex: 5,
                pointerEvents: 'none',
                background: 'linear-gradient(180deg, rgba(255,255,255,0.04) 0%, transparent 100%)',
              }} />

              {/* Screen Glow - Reactive to content */}
              <div
                className="absolute inset-x-4 -bottom-8 h-16 pointer-events-none transition-all duration-1000 ease-in-out"
                style={{
                  background: isInResolvedPhase 
                    ? 'radial-gradient(ellipse 200px 100px at 50% 50%, rgba(34, 197, 94, 0.12), transparent)'
                    : isInCriticalPhase
                    ? 'radial-gradient(ellipse 200px 100px at 50% 50%, rgba(239, 68, 68, 0.15), transparent)'
                    : 'none',
                  filter: 'blur(20px)',
                }}
              />

              {/* ============================================================ */}
              {/* SCREEN CONTENT */}
              {/* ============================================================ */}
              <div className="absolute inset-0 overflow-hidden" style={{ borderRadius: '32px' }}>
              
              {/* Layer 1: Lock Screen */}
              <motion.div
                className="absolute inset-0"
                style={{
                  opacity: lockOpacity,
                  scale: lockScale,
                  y: lockY,
                  filter: lockFilter,
                  pointerEvents: 'none'
                }}
              >
                <LockScreen />
              </motion.div>

              {/* Layer 2: Play Store (scrolls internally) */}
              <motion.div
                className="absolute inset-0 overflow-hidden"
                style={{ 
                  opacity: storeOpacity,
                  scale: storeScale,
                  pointerEvents: 'none'
                }}
              >
                <motion.div
                  ref={contentRef}
                  className="absolute inset-x-0 top-0"
                  style={{ y: storeScrollY }}
                >
                  <PlayStoreContent scrollY={0} scrollProgress={0} />
                </motion.div>
              </motion.div>

            </div>
            {/* End of SCREEN CONTENT div */}

          </div>
          {/* End of Screen Area - Content Container */}

            {/* Right Side Buttons */}
            <div style={{
              position: 'absolute',
              right: '-3px',
              top: '120px',
              width: '3px',
              height: '32px',
              background: 'rgba(255,255,255,0.08)',
              borderRadius: '0 2px 2px 0'
            }} />
            <div style={{
              position: 'absolute',
              right: '-3px',
              top: '164px',
              width: '3px',
              height: '32px',
              background: 'rgba(255,255,255,0.08)',
              borderRadius: '0 2px 2px 0'
            }} />
            
            {/* Left Side Power Button */}
            <div style={{
              position: 'absolute',
              left: '-3px',
              top: '140px',
              width: '3px',
              height: '52px',
              background: 'rgba(255,255,255,0.08)',
              borderRadius: '2px 0 0 2px'
            }} />

            {/* Bottom Home Indicator Area */}
            <div style={{
              display: 'flex',
              justifyContent: 'center',
              paddingTop: '8px',
              paddingBottom: '4px',
              position: 'absolute',
              bottom: 0,
              left: 0,
              right: 0
            }}>
              <div style={{
                width: '120px',
                height: '4px',
                borderRadius: '2px',
                background: 'rgba(255,255,255,0.15)'
              }} />
            </div>
          </div>
        </motion.div>
        </div>
      </div>
    </section>
  );
}

export default PhoneMockup;
