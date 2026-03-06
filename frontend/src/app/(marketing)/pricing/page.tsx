"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, ArrowRight, ChevronDown } from "lucide-react";
import Link from "next/link";

const pricingTiers = [
  {
    name: "Free",
    price: "$0",
    period: "/forever",
    description: "Perfect for testing and small projects",
    features: [
      "3 uploads / month",
      "Up to 10,000 reviews per file",
      "AI cluster analysis",
      "Sentiment & severity scoring",
      "CSV export",
      "Basic analytics dashboard",
      "Community support",
    ],
    cta: "Start Free",
    ctaHref: "/login",
    highlight: false,
  },
  {
    name: "Starter",
    price: "$10",
    period: "/month",
    description: "For solo devs and indie makers",
    features: [
      "10 uploads / month",
      "Up to 10,000 reviews per file",
      "AI cluster analysis",
      "Sentiment & severity scoring",
      "CSV export",
      "Full analytics dashboard",
      "Email support",
    ],
    cta: "Get Started",
    ctaHref: "/login",
    highlight: false,
  },
  {
    name: "Pro",
    price: "$25",
    period: "/month",
    description: "For teams analyzing user feedback regularly",
    features: [
      "50 uploads / month",
      "Up to 100,000 reviews per file",
      "Advanced cluster insights",
      "Priority & noise filtering",
      "AI Debug Center access",
      "Data export (CSV / JSON)",
      "Upload history & archive",
      "Email support",
    ],
    cta: "Start Free Trial",
    ctaHref: "/login",
    highlight: true,
  },
  {
    name: "Business",
    price: "$49",
    period: "/month",
    description: "For high-volume teams and product orgs",
    features: [
      "100 uploads / month",
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
    ctaHref: "/login",
    highlight: false,
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    description: "For organisations with enterprise-scale needs",
    features: [
      "Unlimited uploads",
      "Unlimited reviews per file",
      "Everything in Business",
      "Dedicated infrastructure",
      "Custom integrations",
      "SSO & advanced security",
      "Onboarding & training",
      "Custom SLA",
    ],
    cta: "Contact Sales",
    ctaHref: "mailto:hello@roast.systems",
    highlight: false,
  },
];

const faqs = [
  {
    question: "Can I change plans later?",
    answer:
      "Yes — upgrade or downgrade at any time. Changes take effect immediately and you're only billed for the new plan going forward.",
  },
  {
    question: "What happens if I exceed my upload or review limit?",
    answer:
      "Uploads over your monthly limit are hard-blocked with an upgrade prompt. We'll also warn you when you hit 80% so you're never caught off-guard.",
  },
  {
    question: "What counts as a 'review'?",
    answer:
      "Each row in your uploaded CSV counts as one review. Our noise filter removes low-quality entries before analysis, but the raw row count is used for limit checks.",
  },
  {
    question: "Is the 14-day free trial on all paid plans?",
    answer:
      "Yes — every paid plan (Starter, Pro, Business) includes a 14-day free trial. No credit card required to start.",
  },
  {
    question: "Do you offer refunds?",
    answer:
      "Yes, we offer a 30-day money-back guarantee on all paid plans, no questions asked.",
  },
  {
    question: "Is there a contract or lock-in?",
    answer:
      "No contracts. All plans are month-to-month and you can cancel any time from your account settings.",
  },
  {
    question: "What file formats do you support?",
    answer:
      "CSV is the primary format. Your file must contain a text column with review content. Column names like 'review', 'content', 'text', or 'comment' are auto-detected.",
  },
  {
    question: "How does the AI analysis work?",
    answer:
      "Roast runs your reviews through a noise filter, groups them into semantic clusters using vector embeddings, assigns severity scores (Critical → Low), and generates a root cause analysis for each cluster using an LLM.",
  },
  {
    question: "Can I use Roast for apps on any platform?",
    answer:
      "Yes — any review data in CSV format works. Google Play, App Store, Trustpilot, G2, Capterra, internal surveys — if you can export it to CSV, Roast can analyse it.",
  },
  {
    question: "What is the AI Debug Center?",
    answer:
      "The AI Debug Center (Pro+) gives you per-cluster root cause analysis, suggested fixes and code-level hints, severity reasoning, and exportable GitHub issue templates.",
  },
  {
    question: "Is my data private?",
    answer:
      "Your uploaded data is processed in your account's isolated context, never used to train shared models, and deleted from processing storage after analysis completes.",
  },
  {
    question: "Do you offer discounts for startups or students?",
    answer:
      "Yes — reach out at hello@roast.systems with proof of student status or Y Combinator / accelerator membership and we'll sort you out.",
  },
];

function FAQItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border border-neutral-800 rounded-xl overflow-hidden">
      <button
        className="w-full flex items-center justify-between gap-4 px-6 py-5 text-left hover:bg-neutral-900/60 transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="text-base font-semibold text-white">{question}</span>
        <ChevronDown
          className={`w-5 h-5 flex-shrink-0 text-neutral-400 transition-transform duration-300 ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <p className="px-6 pb-5 text-neutral-400 text-sm leading-relaxed">
              {answer}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function PricingCard({
  tier,
  index,
}: {
  tier: (typeof pricingTiers)[number];
  index: number;
}) {
  return (
    <motion.div
      className={`relative flex flex-col rounded-2xl p-7 ${
        tier.highlight
          ? "bg-gradient-to-b from-orange-500/10 to-red-600/5 border-2 border-orange-500/60 shadow-lg shadow-orange-500/10"
          : "bg-neutral-900/50 border border-neutral-800"
      }`}
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: index * 0.08 }}
      whileHover={{ y: -4, transition: { duration: 0.2 } }}
    >
      {/* Badge sits inside the card — never clips */}
      {tier.highlight && (
        <div className="mb-4">
          <span className="inline-block px-3 py-1 text-xs font-bold tracking-widest uppercase bg-gradient-to-r from-orange-500 to-red-600 rounded-full text-white">
            Most Popular
          </span>
        </div>
      )}

      <div className="mb-5">
        <h3 className="text-xl font-bold uppercase tracking-wide mb-1">{tier.name}</h3>
        <p className="text-neutral-400 text-sm leading-snug">{tier.description}</p>
      </div>

      <div className="mb-6 flex items-end gap-1">
        <span className="text-4xl font-extrabold">{tier.price}</span>
        {tier.period && (
          <span className="text-neutral-400 text-sm pb-1">{tier.period}</span>
        )}
      </div>

      <ul className="space-y-3 mb-8 flex-1">
        {tier.features.map((feature) => (
          <li key={feature} className="flex items-start gap-2.5">
            <Check className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
            <span className="text-neutral-300 text-sm">{feature}</span>
          </li>
        ))}
      </ul>

      <Link href={tier.ctaHref}>
        <motion.button
          className={`w-full py-2.5 px-5 rounded-full font-semibold text-sm flex items-center justify-center gap-2 uppercase tracking-wider transition-colors ${
            tier.highlight
              ? "bg-gradient-to-r from-orange-500 to-red-600 text-white hover:opacity-90"
              : "bg-neutral-800 text-white hover:bg-neutral-700"
          }`}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.97 }}
        >
          {tier.cta}
          <ArrowRight className="w-4 h-4" />
        </motion.button>
      </Link>
    </motion.div>
  );
}

export default function PricingPage() {
  return (
    <div className="min-h-screen bg-black text-white">
      {/* Header */}
      <section className="pt-32 pb-16 text-center px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <h1 className="text-5xl md:text-6xl font-bold tracking-tight uppercase mb-4">
            Simple, Transparent{" "}
            <span className="bg-gradient-to-r from-orange-500 to-red-600 bg-clip-text text-transparent">
              Pricing
            </span>
          </h1>
          <p className="text-neutral-400 text-lg max-w-xl mx-auto">
            Choose the plan that fits your needs. All paid plans include a 14-day free trial.
          </p>
        </motion.div>
      </section>

      {/* Pricing Cards — top row (3) + bottom row (2 centred) */}
      <section className="pb-24 px-6">
        <div className="max-w-screen-xl mx-auto">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 mb-6">
            {pricingTiers.slice(0, 3).map((tier, index) => (
              <PricingCard key={tier.name} tier={tier} index={index} />
            ))}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 max-w-2xl mx-auto">
            {pricingTiers.slice(3).map((tier, index) => (
              <PricingCard key={tier.name} tier={tier} index={index + 3} />
            ))}
          </div>
        </div>
      </section>

      {/* FAQ — accordion */}
      <section className="pb-32 px-6">
        <div className="max-w-3xl mx-auto">
          <motion.h2
            className="text-3xl font-bold text-center mb-10"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            Frequently Asked Questions
          </motion.h2>
          <div className="space-y-3">
            {faqs.map((faq) => (
              <FAQItem key={faq.question} question={faq.question} answer={faq.answer} />
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
