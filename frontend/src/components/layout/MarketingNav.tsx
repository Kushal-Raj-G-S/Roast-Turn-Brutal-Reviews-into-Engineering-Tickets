"use client";

/**
 * MarketingNav - Simple Landing Page Navigation
 * ==============================================
 * Minimal, floating navigation for the marketing site.
 */

import { motion } from "framer-motion";
import Link from "next/link";
import Image from "next/image";
import { ArrowRight } from "lucide-react";

export function MarketingNav() {
  return (
    <motion.nav
      className="fixed top-6 left-1/2 -translate-x-1/2 z-50"
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, delay: 0.2 }}
    >
      <div
        className="flex items-center gap-8 px-6 py-3 rounded-full backdrop-blur-xl bg-black/30 border border-white/10"
        style={{
          boxShadow: "0 8px 32px rgba(0, 0, 0, 0.4)",
        }}
      >
        {/* Logo */}
        <Link href="/" className="flex items-center gap-3">
          <Image 
            src="/logo.png" 
            alt="ROAST Logo" 
            width={40} 
            height={40}
            className="object-contain"
            priority
          />
          <span className="font-black text-2xl bg-gradient-to-r from-orange-500 to-red-600 bg-clip-text text-transparent font-display tracking-tighter">
            ROAST
          </span>
        </Link>

        {/* Nav Links */}
        <div className="hidden md:flex items-center gap-6">
          <Link
            href="#features"
            className="text-sm text-neutral-400 hover:text-white transition-colors font-heading"
          >
            Features
          </Link>
          <Link
            href="#pricing"
            className="text-sm text-neutral-400 hover:text-white transition-colors font-heading"
          >
            Pricing
          </Link>
          <Link
            href="#docs"
            className="text-sm text-neutral-400 hover:text-white transition-colors font-heading"
          >
            Docs
          </Link>
        </div>

        {/* CTA */}
        <Link href="/login">
          <motion.button
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-gradient-to-r from-orange-500 to-red-600 rounded-full font-display tracking-wider"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            style={{
              boxShadow: "0 0 20px rgba(255, 85, 0, 0.4)",
            }}
          >
            Get Started
            <ArrowRight className="w-4 h-4" />
          </motion.button>
        </Link>
      </div>
    </motion.nav>
  );
}

export default MarketingNav;
