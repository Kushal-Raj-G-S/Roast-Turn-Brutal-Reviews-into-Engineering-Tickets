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

import { useRef, useState, useEffect } from "react";
import { motion, useScroll, useTransform, useMotionValue } from "framer-motion";

// ============================================================================
// SCROLL PHASES
// ============================================================================

const PHASE = {
  LOCK_START: 0.0,
  LOCK_END: 0.25,

  UNLOCK_START: 0.25,
  UNLOCK_END: 0.4,

  SCROLL_START: 0.35,
  SCROLL_END: 1.0,
} as const;

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

  useEffect(() => {
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
        >
          {hours}:{minutes}
        </motion.div>
        <motion.div 
          className="text-sm text-neutral-400 mt-3 font-mono tracking-wider"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3, duration: 0.6 }}
        >
          {time.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
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

  const severityColors = {
    critical: 'bg-red-500/20 text-red-400 border-red-500/30',
    high: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
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
        className={`inline-block px-2 py-0.5 rounded-full text-[7px] font-black uppercase tracking-widest mb-1.5 border font-display ${severityColors[review.severity]}`}
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
      className="absolute inset-x-0 top-0 flex flex-col bg-[#0a0a0a] p-4 pt-8"
      style={{ transform: `translateY(${scrollY}px)` }}
    >
      {/* Status Bar */}
      <div className="flex items-center justify-between text-[9px] text-neutral-500 mb-3">
        <motion.span 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="font-medium"
        >
          9:41
        </motion.span>
        <div className="flex items-center gap-1.5">
          <div className="flex gap-0.5">
            <motion.div initial={{ height: 0 }} animate={{ height: 6 }} transition={{ delay: 0.1 }} className="w-1 h-1.5 bg-neutral-500 rounded-sm" />
            <motion.div initial={{ height: 0 }} animate={{ height: 8 }} transition={{ delay: 0.15 }} className="w-1 h-2 bg-neutral-500 rounded-sm" />
            <motion.div initial={{ height: 0 }} animate={{ height: 10 }} transition={{ delay: 0.2 }} className="w-1 h-2.5 bg-neutral-500 rounded-sm" />
            <motion.div initial={{ height: 0 }} animate={{ height: 12 }} transition={{ delay: 0.25 }} className="w-1 h-3 bg-neutral-400 rounded-sm" />
          </div>
          <motion.div 
            initial={{ opacity: 0, scale: 0.5 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.3 }}
            className="w-5 h-2 border border-neutral-500 rounded-sm relative"
          >
            <div className="absolute inset-0.5 right-0.5 bg-green-500 rounded-[1px]" />
          </motion.div>
        </div>
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

      {/* FULL SCREEN MEME - Stays visible */}
      <div className="my-8 relative h-[500px] rounded-2xl overflow-hidden">
        <img
          src="/meme.jpg"
          alt="A Few Moments Later"
          className="absolute inset-0 w-full h-full object-cover"
        />
      </div>

      {/* Spacer */}
      <div className="h-16" />

      {/* PROFESSIONAL "AFTER USING ROAST" SCREEN */}
      <motion.div
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: false, amount: 0.5 }}
        transition={{ duration: 0.5 }}
        className="my-8 flex flex-col items-center justify-center py-20 bg-gradient-to-br from-neutral-900 to-black rounded-2xl border border-neutral-800"
      >
        <motion.img
          src="/logo.png"
          alt="ROAST"
          initial={{ scale: 0.8, opacity: 0 }}
          whileInView={{ scale: 1, opacity: 1 }}
          viewport={{ once: false }}
          transition={{ duration: 0.4, type: "spring", stiffness: 200 }}
          className="w-20 h-20 mb-6"
        />
        <motion.h3
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: false }}
          transition={{ duration: 0.3, delay: 0.1 }}
          className="text-2xl font-black text-white mb-3 font-heading"
        >
          After Using ROAST
        </motion.h3>
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: false }}
          transition={{ duration: 0.3, delay: 0.2 }}
          className="text-sm text-neutral-400 font-sans"
        >
          All issues resolved
        </motion.p>
      </motion.div>

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

export function PhoneMockup() {
  const containerRef = useRef<HTMLDivElement>(null);

  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start start", "end end"],
  });

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
  // PHASE 1: LOCK SCREEN (0.0 → 0.2)
  // ==========================================================================

  const lockOpacity = useTransform(
    scrollYProgress,
    [PHASE.LOCK_START, PHASE.LOCK_END - 0.05, PHASE.LOCK_END],
    [1, 1, 0]
  );

  const lockScale = useTransform(
    scrollYProgress,
    [PHASE.LOCK_END - 0.1, PHASE.LOCK_END],
    [1, 1.1]
  );

  // ==========================================================================
  // PHASE 2: UNLOCK → PLAY STORE (0.2 → 0.35)
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
  // PHASE 3: PLAY STORE SCROLLS (0.35 → 1.0)
  // ==========================================================================

  const SCROLL_DISTANCE = 3400;

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
  // RENDER
  // ==========================================================================

  return (
    <section ref={containerRef} className="relative h-[800vh]">
      {/* Sticky Container - Below Navbar */}
      <div className="sticky top-20 h-[calc(100vh-5rem)] flex items-center justify-center overflow-hidden px-4">
        
        {/* Background */}
        <div className="absolute inset-0 bg-gradient-to-b from-neutral-950 via-neutral-900 to-neutral-950" />

        {/* LEFT SIDE ANNOTATIONS */}
        <div className="absolute left-8 top-1/2 -translate-y-1/2 max-w-xs space-y-8 hidden xl:block">
          <motion.div style={{ opacity: leftAnnotation1Opacity, x: useTransform(leftAnnotation1Opacity, [0, 1], [-20, 0]) }}>
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-full bg-red-500/20 flex items-center justify-center shrink-0">
                <svg className="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <div>
                <p className="text-sm font-semibold text-white">Real Problems</p>
                <p className="text-xs text-neutral-400 leading-relaxed">
                  Every negative review represents a real user facing a real issue
                </p>
              </div>
            </div>
          </motion.div>

          <motion.div style={{ opacity: leftAnnotation2Opacity, x: useTransform(leftAnnotation2Opacity, [0, 1], [-20, 0]) }}>
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-full bg-orange-500/20 flex items-center justify-center shrink-0">
                <svg className="w-5 h-5 text-orange-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
              </div>
              <div>
                <p className="text-sm font-semibold text-white">Auto-Clustering</p>
                <p className="text-xs text-neutral-400 leading-relaxed">
                  ROAST groups similar complaints automatically
                </p>
              </div>
            </div>
          </motion.div>

          <motion.div style={{ opacity: leftAnnotation3Opacity, x: useTransform(leftAnnotation3Opacity, [0, 1], [-20, 0]) }}>
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-full bg-emerald-500/20 flex items-center justify-center shrink-0">
                <svg className="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div>
                <p className="text-sm font-semibold text-white">Instant Tickets</p>
                <p className="text-xs text-neutral-400 leading-relaxed">
                  Tickets ready for your engineering team to act on
                </p>
              </div>
            </div>
          </motion.div>
        </div>

        {/* RIGHT SIDE ANNOTATIONS */}
        <div className="absolute right-8 top-1/2 -translate-y-1/2 max-w-xs space-y-8 hidden xl:block">
          <motion.div style={{ opacity: rightAnnotation1Opacity, x: useTransform(rightAnnotation1Opacity, [0, 1], [20, 0]) }}>
            <div className="flex items-start gap-3">
              <div>
                <p className="text-sm font-semibold text-white text-right">Stop Losing Users</p>
                <p className="text-xs text-neutral-400 leading-relaxed text-right">
                  These reviews cost you revenue. Fix them before they spiral.
                </p>
              </div>
              <div className="w-10 h-10 rounded-full bg-purple-500/20 flex items-center justify-center shrink-0">
                <svg className="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                </svg>
              </div>
            </div>
          </motion.div>

          <motion.div style={{ opacity: rightAnnotation2Opacity, x: useTransform(rightAnnotation2Opacity, [0, 1], [20, 0]) }}>
            <div className="flex items-start gap-3">
              <div>
                <p className="text-sm font-semibold text-white text-right">Priority Sorting</p>
                <p className="text-xs text-neutral-400 leading-relaxed text-right">
                  Critical issues bubble up automatically based on impact
                </p>
              </div>
              <div className="w-10 h-10 rounded-full bg-blue-500/20 flex items-center justify-center shrink-0">
                <svg className="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12" />
                </svg>
              </div>
            </div>
          </motion.div>

          <motion.div style={{ opacity: rightAnnotation3Opacity, x: useTransform(rightAnnotation3Opacity, [0, 1], [20, 0]) }}>
            <div className="flex items-start gap-3">
              <div>
                <p className="text-sm font-semibold text-white text-right">Ship Faster</p>
                <p className="text-xs text-neutral-400 leading-relaxed text-right">
                  No more manual review analysis. Focus on building fixes.
                </p>
              </div>
              <div className="w-10 h-10 rounded-full bg-pink-500/20 flex items-center justify-center shrink-0">
                <svg className="w-5 h-5 text-pink-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
            </div>
          </motion.div>
        </div>

        {/* ================================================================ */}
        {/* PHONE SHELL */}
        {/* ================================================================ */}
        <motion.div
          className="relative z-10"
          style={{
            width: PHONE.WIDTH,
            height: PHONE.HEIGHT,
            scale: phoneScale,
            borderRadius: phoneBorderRadius,
            boxShadow: phoneShadow,
          }}
        >
          {/* Phone Body */}
          <motion.div
            className="absolute inset-0 bg-neutral-900 overflow-hidden"
            style={{ borderRadius: phoneBorderRadius }}
          >
            {/* Bezel */}
            <div 
              className="absolute inset-0 border border-neutral-700/30 pointer-events-none z-50"
              style={{ borderRadius: "inherit" }}
            />

            {/* Notch */}
            <div className="absolute top-0 left-1/2 -translate-x-1/2 z-50">
              <div 
                className="bg-black rounded-b-xl flex items-center justify-center"
                style={{ width: PHONE.NOTCH_WIDTH, height: PHONE.NOTCH_HEIGHT }}
              >
                <div className="w-2 h-2 rounded-full bg-neutral-800" />
              </div>
            </div>

            {/* Home Indicator */}
            <div className="absolute bottom-1.5 left-1/2 -translate-x-1/2 w-20 h-1 bg-neutral-700 rounded-full z-50" />

            {/* ============================================================ */}
            {/* SCREEN CONTENT */}
            {/* ============================================================ */}
            <div className="absolute inset-0 overflow-hidden" style={{ borderRadius: "inherit" }}>
              
              {/* Layer 1: Lock Screen */}
              <motion.div
                className="absolute inset-0"
                style={{ 
                  opacity: lockOpacity,
                  scale: lockScale,
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
                }}
              >
                <motion.div
                  className="absolute inset-x-0 top-0"
                  style={{ y: storeScrollY }}
                >
                  <PlayStoreContent scrollY={0} scrollProgress={scrollYProgress.get()} />
                </motion.div>
              </motion.div>

            </div>
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}

export default PhoneMockup;
