"use client";

/**
 * Marketing Landing Page - Scroll-Driven Cinematic Experience
 * ============================================================
 * Apple-style scroll narrative with PhoneMockup hero + Authentication
 */

import { motion, useMotionValue, useSpring } from "framer-motion";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Zap, Brain, Target, Layers, Sparkles, Shield } from "lucide-react";
import { GoogleIcon, GithubIcon } from "@/components/ui/BrandIcons";
import { SpotlightCard } from "@/components/ui";
import { PipelineScrollWorld } from "@/components/landing/PipelineScrollWorld";
import { supabase } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";

const features = [
  {
    title: "AI-Powered Clustering",
    description: "Automatically groups similar reviews into actionable clusters using semantic embeddings.",
    icon: Brain,
    span: "col-span-2",
  },
  {
    title: "Sentiment & Severity Analysis",
    description: "Automatic sentiment scoring and severity classification (critical, high, medium, low) for every cluster.",
    icon: Target,
    span: "col-span-1",
  },
  {
    title: "Noise Filtering",
    description: "Smart filtering removes spam, duplicates, and irrelevant reviews before analysis.",
    icon: Shield,
    span: "col-span-1",
  },
  {
    title: "CSV Upload",
    description: "Upload any review dataset as CSV. Auto-detects text and rating columns - zero configuration needed.",
    icon: Layers,
    span: "col-span-1",
  },
  {
    title: "Cluster Summaries",
    description: "AI-generated summaries for each cluster with sample reviews and key insights.",
    icon: Sparkles,
    span: "col-span-1",
  },
  {
    title: "Analytics Dashboard",
    description: "Real-time processing status, cluster distribution, sentiment breakdown, and severity metrics.",
    icon: Zap,
    span: "col-span-2",
  },
];

export default function MarketingPage() {
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  
  // Cursor tracking for interactive background (only after phone mockup)
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);
  const [showBlobs, setShowBlobs] = useState(false);
  
  const springConfig = { damping: 25, stiffness: 150 };
  const x = useSpring(mouseX, springConfig);
  const y = useSpring(mouseY, springConfig);

  useEffect(() => {
    // Check if user is authenticated
    const checkAuth = async () => {
      const { data: { user } } = await supabase.auth.getUser();
      setIsAuthenticated(!!user);
    };
    checkAuth();

    // Listen to auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      setIsAuthenticated(!!session);
    });

    return () => subscription.unsubscribe();
  }, []);

  useEffect(() => {
    const handleScroll = () => {
      // Show blobs only after scrolling past phone mockup section (800vh = 8x viewport)
      const scrolled = window.scrollY;
      const phoneMockupHeight = window.innerHeight * 8; // 800vh converted to px
      setShowBlobs(scrolled > phoneMockupHeight * 0.95);
    };

    window.addEventListener('scroll', handleScroll);
    handleScroll(); // Check initial state
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Handle Google Sign In
  const handleGoogleSignIn = async () => {
    try {
      setIsLoading(true);
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/api/auth/callback`,
        },
      });
      if (error) throw error;
    } catch (error) {
      console.error('Error signing in:', error);
      setIsLoading(false);
    }
  };

  // Handle GitHub Sign In
  const handleGithubSignIn = async () => {
    try {
      setIsLoading(true);
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'github',
        options: {
          redirectTo: `${window.location.origin}/api/auth/callback`,
        },
      });
      if (error) throw error;
    } catch (error) {
      console.error('Error signing in:', error);
      setIsLoading(false);
    }
  };

  return (
    <div 
      className="relative bg-neutral-950"
      onMouseMove={(e) => {
        if (showBlobs) {
          mouseX.set(e.clientX);
          mouseY.set(e.clientY);
        }
      }}
    >
      {/* Continuous cursor-following background (only visible after phone mockup) */}
      {showBlobs && (
        <>
          <motion.div
            className="fixed w-[600px] h-[600px] rounded-full opacity-30 blur-3xl pointer-events-none z-10"
            style={{
              background: "radial-gradient(circle, rgba(255,85,0,0.8) 0%, rgba(255,46,0,0.4) 50%, transparent 100%)",
              x,
              y,
              translateX: "-50%",
              translateY: "-50%",
            }}
          />
          
          {/* Secondary smaller blob */}
          <motion.div
            className="fixed w-[400px] h-[400px] rounded-full opacity-25 blur-2xl pointer-events-none z-10"
            style={{
              background: "radial-gradient(circle, rgba(255,136,0,0.7) 0%, rgba(255,85,0,0.3) 50%, transparent 100%)",
              x,
              y,
              translateX: "-30%",
              translateY: "-30%",
            }}
          />
        </>
      )}

      {/* ================================================================== */}
      {/* PIPELINE SCROLL WORLD - Scroll-driven flythrough of Roast's own pipeline */}
      {/* ================================================================== */}
      <div className="relative" style={{ isolation: "isolate" }}>
        <PipelineScrollWorld />
      </div>

      {/* ================================================================== */}
      {/* TRANSITION SECTION */}
      {/* ================================================================== */}
      <section className="relative py-32 px-6 bg-gradient-to-b from-neutral-950 to-neutral-900">
        <div className="max-w-4xl mx-auto text-center relative z-20">
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 0.6 }}
          >
            <h2 className="text-4xl md:text-7xl font-black text-white mb-6 font-playfair tracking-tight leading-[0.95]" style={{ fontWeight: 900 }}>
              Stop drowning in{" "}
              <span className="text-gradient-fire font-playfair italic">complaints</span>
            </h2>
            <p className="text-lg md:text-xl text-neutral-300 max-w-2xl mx-auto mb-10 font-sans tracking-normal leading-relaxed">
              Every negative review is a bug report in disguise. ROAST reads them all, 
              clusters the chaos, and hands you clean engineering tickets.
            </p>
            
            {/* CTA Buttons - Show different options based on auth state */}
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              {isAuthenticated ? (
                <Link
                  href="/dashboard"
                  className="group flex items-center gap-3 px-10 py-5 rounded-full bg-gradient-to-r from-orange-500 to-red-600 text-white font-bold hover:shadow-xl hover:shadow-orange-500/30 transition-all duration-300 font-display text-sm tracking-wider"
                >
                  Go to Dashboard
                  <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </Link>
              ) : (
                <>
                  <button
                    onClick={handleGoogleSignIn}
                    disabled={isLoading}
                    className="group flex items-center gap-3 px-10 py-5 rounded-full bg-white text-black font-bold hover:shadow-xl hover:shadow-white/20 transition-all duration-300 font-display text-sm tracking-wider disabled:opacity-50"
                  >
                    <GoogleIcon className="w-5 h-5" />
                    Sign in with Google
                  </button>
                  <button
                    onClick={handleGithubSignIn}
                    disabled={isLoading}
                    className="group flex items-center gap-3 px-10 py-5 rounded-full bg-neutral-800 border border-white/10 text-white font-bold hover:bg-neutral-700 transition-all duration-300 font-display text-sm tracking-wider disabled:opacity-50"
                  >
                    <GithubIcon className="w-5 h-5" />
                    Sign in with GitHub
                  </button>
                </>
              )}
            </div>
            
            {!isAuthenticated && (
              <p className="text-sm text-neutral-500 mt-6">
                Or{" "}
                <Link href="/login" className="text-orange-400 hover:text-orange-300 underline">
                  sign in with email
                </Link>
              </p>
            )}
          </motion.div>

          {/* Stats */}
          <motion.div
            className="grid grid-cols-3 gap-8 max-w-xl mx-auto mt-20"
          >
            {[
              { value: "10M+", label: "Reviews Processed" },
              { value: "500+", label: "Teams Using" },
              { value: "87%", label: "Time Saved" },
            ].map((stat, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 40 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-50px" }}
                transition={{ duration: 0.6, delay: 0.2 + i * 0.1 }}
                className="text-center"
              >
                <div className="text-3xl font-black text-white font-display tracking-wider">{stat.value}</div>
                <div className="text-sm text-neutral-500 font-heading">{stat.label}</div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ================================================================== */}
      {/* FEATURES BENTO GRID */}
      {/* ================================================================== */}
      <section id="features" className="relative py-32 px-6 bg-neutral-900">
        <div className="max-w-6xl mx-auto relative z-20">
          {/* Section Header */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="text-center mb-16"
          >
            <div className="text-spaced mb-4 tracking-[0.25em]">BUILT FOR ENGINEERING TEAMS</div>
            <h2 className="text-4xl md:text-6xl font-black text-white mb-4 font-playfair tracking-tight" style={{ fontWeight: 900 }}>
              Everything You Need
            </h2>
            <p className="text-lg md:text-xl text-neutral-300 max-w-xl mx-auto font-sans tracking-normal">
              From raw CSV to prioritized tickets in seconds. Here's how Roast supercharges your workflow.
            </p>
          </motion.div>

          {/* Bento Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {features.map((feature, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 40 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-50px" }}
                transition={{ duration: 0.6, delay: i * 0.1 }}
                className={feature.span}
              >
                <SpotlightCard className="h-full p-6 feature-card">
                  <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-orange-500/20 to-red-500/20 border border-orange-500/20 flex items-center justify-center mb-4">
                    <feature.icon className="w-6 h-6 text-orange-400" />
                  </div>
                  <h3 className="text-lg font-bold text-white mb-2 font-heading">
                    {feature.title}
                  </h3>
                  <p className="text-sm text-neutral-400 font-sans">
                    {feature.description}
                  </p>
                </SpotlightCard>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ================================================================== */}
      {/* CTA SECTION */}
      {/* ================================================================== */}
      <section className="relative py-32 px-6 bg-neutral-950">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="max-w-4xl mx-auto relative z-20"
        >
          <div className="relative rounded-3xl bg-gradient-to-br from-orange-500/10 via-red-500/10 to-pink-500/10 border border-white/10 p-12 md:p-20 text-center overflow-hidden rotating-gradient">
            <h2 className="relative text-4xl md:text-5xl font-black text-white mb-4 font-playfair" style={{ fontWeight: 900 }}>
              Ready to Stop Reading Reviews?
            </h2>
            <p className="relative text-lg text-neutral-400 max-w-xl mx-auto mb-8">
              Join hundreds of teams who've automated their review-to-ticket pipeline.
            </p>
            <Link
              href="/dashboard"
              className="relative inline-flex items-center gap-2 px-10 py-5 rounded-full bg-white text-black font-bold hover:scale-105 transition-transform cta-button-glow"
            >
              Get Started Free
              <ArrowRight className="w-5 h-5" />
            </Link>
          </div>
        </motion.div>
      </section>
    </div>
  );
}
