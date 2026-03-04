"use client";

/**
 * Pricing Page - Transparent and Simple Pricing
 * ==============================================
 * Three-tier pricing with feature comparison
 */

import { motion } from "framer-motion";
import { Check, ArrowRight } from "lucide-react";
import Link from "next/link";

const pricingTiers = [
  {
    name: "Free",
    price: "$0",
    period: "/forever",
    description: "Perfect for testing and small projects",
    features: [
      "Up to 5 dataset uploads",
      "AI-powered cluster analysis",
      "Sentiment & severity scoring",
      "CSV export",
      "Basic analytics dashboard",
      "Community support",
    ],
    cta: "Start Free",
    highlight: false,
  },
  {
    name: "Pro",
    price: "$49",
    period: "/month",
    description: "For teams analyzing user feedback regularly",
    features: [
      "Up to 30 dataset uploads/month",
      "Advanced cluster insights",
      "Priority & noise filtering",
      "Full analytics dashboard",
      "Email support",
      "Data export (CSV/JSON)",
      "Upload history & archive",
    ],
    cta: "Start Free Trial",
    highlight: true,
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    description: "For organizations with high-volume needs",
    features: [
      "Unlimited dataset uploads",
      "Dedicated processing infrastructure",
      "Custom cluster models",
      "API access",
      "Priority support (24/7)",
      "Custom integrations",
      "Team collaboration tools",
      "SLA guarantees",
    ],
    cta: "Contact Sales",
    highlight: false,
  },
];

export default function PricingPage() {
  return (
    <div className="min-h-screen bg-black text-white">
      {/* Header Section */}
      <section className="relative pt-32 pb-20">
        <div className="max-w-7xl mx-auto px-6">
          <motion.div
            className="text-center"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <h1 className="text-5xl md:text-6xl font-bold mb-6 tracking-tight uppercase">
              Simple, Transparent{" "}
              <span className="bg-gradient-to-r from-orange-500 to-red-600 bg-clip-text text-transparent">
                Pricing
              </span>
            </h1>
            <p className="text-lg text-neutral-400 max-w-2xl mx-auto">
              Choose the plan that fits your needs. All plans include a 14-day free trial.
            </p>
          </motion.div>
        </div>
      </section>

      {/* Pricing Cards */}
      <section className="relative pb-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {pricingTiers.map((tier, index) => (
              <motion.div
                key={tier.name}
                className={`relative rounded-2xl p-8 ${
                  tier.highlight
                    ? "bg-gradient-to-br from-orange-500/10 to-red-600/10 border-2 border-orange-500/50"
                    : "bg-neutral-900/50 border border-neutral-800"
                }`}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: index * 0.1 }}
                whileHover={{ y: -5 }}
              >
                {tier.highlight && (
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2">
                    <span className="px-4 py-1 text-xs font-bold bg-gradient-to-r from-orange-500 to-red-600 rounded-full">
                      MOST POPULAR
                    </span>
                  </div>
                )}

                <div className="mb-8">
                  <h3 className="text-2xl font-bold mb-2 uppercase tracking-wide">{tier.name}</h3>
                  <p className="text-neutral-400 text-sm">{tier.description}</p>
                </div>

                <div className="mb-8">
                  <span className="text-5xl font-bold">{tier.price}</span>
                  <span className="text-neutral-400">{tier.period}</span>
                </div>

                <ul className="space-y-4 mb-8">
                  {tier.features.map((feature) => (
                    <li key={feature} className="flex items-start gap-3">
                      <Check className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" />
                      <span className="text-neutral-300">{feature}</span>
                    </li>
                  ))}
                </ul>

                <Link href="/login" className="block">
                  <motion.button
                    className={`w-full py-3 px-6 rounded-full font-semibold flex items-center justify-center gap-2 uppercase tracking-wider text-sm ${
                      tier.highlight
                        ? "bg-gradient-to-r from-orange-500 to-red-600 text-white"
                        : "bg-neutral-800 text-white hover:bg-neutral-700"
                    }`}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    {tier.cta}
                    <ArrowRight className="w-4 h-4" />
                  </motion.button>
                </Link>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ Section */}
      <section className="relative pb-32">
        <div className="max-w-4xl mx-auto px-6">
          <motion.h2
            className="text-3xl font-bold mb-12 text-center"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            Frequently Asked Questions
          </motion.h2>

          <div className="space-y-6">
            {[
              {
                question: "Can I change plans later?",
                answer: "Yes! You can upgrade or downgrade at any time. Changes take effect immediately.",
              },
              {
                question: "What happens if I exceed my review limit?",
                answer: "We'll notify you when you reach 80% of your limit. You can upgrade anytime to avoid interruptions.",
              },
              {
                question: "Do you offer refunds?",
                answer: "Yes, we offer a 30-day money-back guarantee on all annual plans.",
              },
              {
                question: "Is there a contract?",
                answer: "No contracts. All plans are month-to-month and you can cancel anytime.",
              },
            ].map((faq, index) => (
              <motion.div
                key={index}
                className="bg-neutral-900/50 border border-neutral-800 rounded-xl p-6"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: index * 0.1 }}
              >
                <h3 className="text-lg font-bold mb-2">{faq.question}</h3>
                <p className="text-neutral-400">{faq.answer}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
