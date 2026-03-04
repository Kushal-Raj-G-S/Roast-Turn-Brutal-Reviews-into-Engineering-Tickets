"use client";

/**
 * MarketingFooter - Simple Footer for Marketing Site
 * ===================================================
 */

import Link from "next/link";
import { Github, Twitter, Mail } from "lucide-react";

export function MarketingFooter() {
  return (
    <footer className="relative z-10 border-t border-white/5 bg-black/20 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-6 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          {/* Brand */}
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-orange-500 to-red-600 flex items-center justify-center">
                <span className="text-white font-black text-sm">🔥</span>
              </div>
              <span className="font-black text-xl bg-gradient-to-r from-orange-500 to-red-600 bg-clip-text text-transparent">
                ROAST
              </span>
            </div>
            <p className="text-sm text-neutral-500 max-w-xs">
              Turn brutal user reviews into actionable engineering tickets with AI.
            </p>
          </div>

          {/* Product */}
          <div>
            <h4 className="font-semibold text-white mb-4">Product</h4>
            <ul className="space-y-2">
              <li>
                <Link href="/#features" className="text-sm text-neutral-500 hover:text-white transition-colors">
                  Features
                </Link>
              </li>
              <li>
                <Link href="/pricing" className="text-sm text-neutral-500 hover:text-white transition-colors">
                  Pricing
                </Link>
              </li>
              <li>
                <Link href="/dashboard" className="text-sm text-neutral-500 hover:text-white transition-colors">
                  Dashboard
                </Link>
              </li>
            </ul>
          </div>

          {/* Resources */}
          <div>
            <h4 className="font-semibold text-white mb-4">Resources</h4>
            <ul className="space-y-2">
              <li>
                <Link href="/docs" className="text-sm text-neutral-500 hover:text-white transition-colors">
                  Documentation
                </Link>
              </li>
              <li>
                <Link href="#api" className="text-sm text-neutral-500 hover:text-white transition-colors">
                  API Reference
                </Link>
              </li>
              <li>
                <Link href="#changelog" className="text-sm text-neutral-500 hover:text-white transition-colors">
                  Changelog
                </Link>
              </li>
            </ul>
          </div>

          {/* Connect */}
          <div>
            <h4 className="font-semibold text-white mb-4">Connect</h4>
            <div className="flex items-center gap-4">
              <a
                href="https://github.com"
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 rounded-lg bg-white/5 text-neutral-400 hover:text-white hover:bg-white/10 transition-colors"
              >
                <Github className="w-5 h-5" />
              </a>
              <a
                href="https://twitter.com"
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 rounded-lg bg-white/5 text-neutral-400 hover:text-white hover:bg-white/10 transition-colors"
              >
                <Twitter className="w-5 h-5" />
              </a>
              <a
                href="mailto:hello@roast.dev"
                className="p-2 rounded-lg bg-white/5 text-neutral-400 hover:text-white hover:bg-white/10 transition-colors"
              >
                <Mail className="w-5 h-5" />
              </a>
            </div>
          </div>
        </div>

        {/* Bottom */}
        <div className="mt-12 pt-8 border-t border-white/5 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-sm text-neutral-600">
            © 2026 Roast. All rights reserved.
          </p>
          <div className="flex items-center gap-6">
            <Link href="#privacy" className="text-sm text-neutral-600 hover:text-neutral-400 transition-colors">
              Privacy
            </Link>
            <Link href="#terms" className="text-sm text-neutral-600 hover:text-neutral-400 transition-colors">
              Terms
            </Link>
          </div>
        </div>
      </div>
    </footer>
  );
}

export default MarketingFooter;
