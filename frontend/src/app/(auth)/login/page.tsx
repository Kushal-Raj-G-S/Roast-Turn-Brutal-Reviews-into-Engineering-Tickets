"use client";

/**
 * Login Page - Glassmorphism Auth Card with Supabase
 * ===================================================
 * Features: Google/GitHub OAuth, email auth, animated effects
 */

import { motion } from "framer-motion";
import Link from "next/link";
import { useState } from "react";
import { Mail, Lock, ArrowRight, Chrome, Github, Loader2, AlertCircle } from "lucide-react";
import { supabase } from "@/lib/supabase/client";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  // Handle Google Sign In
  const handleGoogleSignIn = async () => {
    try {
      setIsLoading(true);
      setError("");
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/api/auth/callback`,
        },
      });
      if (error) throw error;
    } catch (error: any) {
      setError(error.message);
      setIsLoading(false);
    }
  };

  // Handle GitHub Sign In
  const handleGithubSignIn = async () => {
    try {
      setIsLoading(true);
      setError("");
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'github',
        options: {
          redirectTo: `${window.location.origin}/api/auth/callback`,
        },
      });
      if (error) throw error;
    } catch (error: any) {
      setError(error.message);
      setIsLoading(false);
    }
  };

  // Handle Email/Password Sign In
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setIsLoading(true);
      setError("");
      
      const { error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });
      
      if (error) throw error;
      
      // Redirect to dashboard
      window.location.href = "/dashboard";
    } catch (error: any) {
      setError(error.message);
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md">
      {/* Logo */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center mb-8"
      >
        <Link href="/" className="inline-flex items-center gap-2">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-orange-500 to-red-600 flex items-center justify-center shadow-lg shadow-orange-500/25">
            <span className="text-2xl">🔥</span>
          </div>
          <span className="font-black text-3xl bg-gradient-to-r from-orange-500 to-red-600 bg-clip-text text-transparent">
            ROAST
          </span>
        </Link>
      </motion.div>

      {/* Glass Card */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="relative rounded-3xl bg-white/5 backdrop-blur-xl border border-white/10 p-8 shadow-2xl"
      >
        {/* Glow Effect */}
        <div className="absolute -top-20 left-1/2 -translate-x-1/2 w-64 h-64 bg-orange-500/20 rounded-full blur-3xl pointer-events-none" />

        {/* Header */}
        <div className="relative text-center mb-8">
          <h1 className="text-2xl font-bold text-white mb-2">Welcome back</h1>
          <p className="text-neutral-400">Sign in to continue roasting</p>
        </div>

        {/* Error Message */}
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="relative mb-6 p-4 rounded-xl bg-red-500/10 border border-red-500/20 flex items-start gap-3"
          >
            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-red-300">{error}</p>
          </motion.div>
        )}

        {/* Social Auth */}
        <div className="relative space-y-3 mb-8">
          <button 
            onClick={handleGoogleSignIn}
            disabled={isLoading}
            className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white font-medium hover:bg-white/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Chrome className="w-5 h-5" />
            Continue with Google
          </button>
          <button 
            onClick={handleGithubSignIn}
            disabled={isLoading}
            className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white font-medium hover:bg-white/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Github className="w-5 h-5" />
            Continue with GitHub
          </button>
        </div>

        {/* Divider */}
        <div className="relative flex items-center gap-4 mb-8">
          <div className="flex-1 h-px bg-white/10" />
          <span className="text-sm text-neutral-500">or</span>
          <div className="flex-1 h-px bg-white/10" />
        </div>

        {/* Email Form */}
        <form onSubmit={handleSubmit} className="relative space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-neutral-400 mb-2">
              Email
            </label>
            <div className="relative">
              <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-500" />
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="w-full pl-12 pr-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder:text-neutral-600 focus:outline-none focus:border-orange-500/50 focus:ring-1 focus:ring-orange-500/50 transition-all"
                required
              />
            </div>
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-neutral-400 mb-2">
              Password
            </label>
            <div className="relative">
              <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-500" />
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-12 pr-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder:text-neutral-600 focus:outline-none focus:border-orange-500/50 focus:ring-1 focus:ring-orange-500/50 transition-all"
                required
              />
            </div>
          </div>

          <div className="flex items-center justify-between text-sm">
            <label className="flex items-center gap-2 text-neutral-400 cursor-pointer">
              <input type="checkbox" className="w-4 h-4 rounded bg-white/5 border-white/10" />
              Remember me
            </label>
            <Link href="/forgot-password" className="text-orange-400 hover:text-orange-300 transition-colors">
              Forgot password?
            </Link>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-gradient-to-r from-orange-500 to-red-600 text-white font-semibold hover:shadow-lg hover:shadow-orange-500/25 disabled:opacity-60 disabled:cursor-not-allowed transition-all"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Signing in...
              </>
            ) : (
              <>
                Sign in
                <ArrowRight className="w-5 h-5" />
              </>
            )}
          </button>
        </form>

        {/* Footer */}
        <p className="relative text-center text-sm text-neutral-500 mt-8">
          Don't have an account?{" "}
          <Link href="/signup" className="text-orange-400 hover:text-orange-300 transition-colors">
            Sign up free
          </Link>
        </p>
      </motion.div>

      {/* Terms */}
      <p className="text-center text-xs text-neutral-600 mt-6">
        By signing in, you agree to our{" "}
        <Link href="#" className="underline hover:text-neutral-400">Terms</Link>
        {" "}and{" "}
        <Link href="#" className="underline hover:text-neutral-400">Privacy Policy</Link>
      </p>
    </div>
  );
}
