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
      "3 dataset uploads/month",
      "Up to 10,000 reviews per file",
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
    name: "Starter",
    price: "$10",
    period: "/month",
    description: "For solo devs and indie makers",
    features: [
      "10 dataset uploads/month",
      "Up to 10,000 reviews per file",
      "AI-powered cluster analysis",
      "Sentiment & severity scoring",
      "CSV export",
      "Full analytics dashboard",
      "Email support",
    ],
    cta: "Get Started",
    highlight: false,
  },
  {
    name: "Pro",
    price: "$25",
    period: "/month",
    description: "For teams analyzing user feedback regularly",
    features: [
      "50 dataset uploads/month",
      "Up to 100,000 reviews per file",
      "Advanced cluster insights",
      "Priority & noise filtering",
      "Full analytics dashboard",
      "AI Debug Center access",
      "Data export (CSV/JSON)",
      "Upload history & archive",
      "Email support",
    ],
    cta: "Start Free Trial",
    highlight: true,
  },
  {
    name: "Business",
    price: "$49",
    period: "/month",
    description: "For high-volume teams and product orgs",
    features: [
      "100 dataset uploads/month",
      "Up to 100,000 reviews per file",
      "Everything in Pro",
      "Dedicated processing priority",
      "API access",
      "Custom cluster models",
      "Team collaboration tools",
      "Priority support (24/7)",
      "SLA guarantees",
    ],
    cta: "Get Business",
    highlight: false,
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    description: "For organizations with enterprise-scale needs",
    features: [
      "Unlimited dataset uploads",
      "Unlimited reviews per file",
      "Everything in Business",
      "Dedicated infrastructure",
      "Custom integrations",
      "SSO & advanced security",
      "Onboarding & training",
      "Custom SLA",
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
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6">
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

                <Link href={tier.name === "Enterprise" ? "mailto:hello@roast.systems" : "/login"} className="block">
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
                answer: "Yes — upgrade or downgrade at any time. Changes take effect immediately and you're only billed for the new plan going forward.",
              },
              {
                question: "What happens if I exceed my upload or review limit?",
                answer: "Uploads over your monthly limit are hard-blocked with an upgrade prompt. We'll also warn you when you hit 80% so you're never caught off-guard.",
              },
              {
                question: "What counts as a 'review'?",
                answer: "Each row in your uploaded CSV counts as one review. Our noise filter removes low-quality entries before analysis, but the raw row count is used for limit checks.",
              },
              {
                question: "Is the 14-day free trial on all paid plans?",
                answer: "Yes — every paid plan (Starter, Pro, Business) includes a 14-day free trial. No credit card required to start.",
              },
              {
                question: "Do you offer refunds?",
                answer: "Yes, we offer a 30-day money-back guarantee on all paid plans, no questions asked.",
              },
              {
                question: "Is there a contract or lock-in?",
                answer: "No contracts. All plans are month-to-month and you can cancel any time from your account settings.",
              },
              {
                question: "What file formats do you support?",
                answer: "CSV is the primary format. Your file must contain a text column with review content. Column names like 'review', 'content', 'text', or 'comment' are auto-detected.",
              },
              {
                question: "How does the AI analysis work?",
                answer: "Roast runs your reviews through a noise filter, groups them into semantic clusters using vector embeddings, assigns severity scores (Critical → Low), and generates a root cause analysis for each cluster using an LLM.",
              },
              {
                question: "Can I use Roast for apps on any platform?",
                answer: "Yes — any review data in CSV format works. Google Play, App Store, Trustpilot, G2, Capterra, internal surveys — if you can export it to CSV, Roast can analyze it.",
              },
              {
                question: "What is the AI Debug Center?",
                answer: "The AI Debug Center (Pro+) gives you per-cluster root cause analysis, suggested fixes and code-level hints, severity reasoning, and exportable github issue templates.",
              },
              {
                question: "Is my data private?",
                answer: "Your uploaded data is processed in your account's isolated context, never used to train shared models, and deleted from processing storage after analysis completes.",
              },
              {
                question: "Do you offer discounts for startups or students?",
                answer: "Yes — reach out at hello@roast.systems with proof of student status or Y Combinator / accelerator membership and we'll sort you out.",
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
