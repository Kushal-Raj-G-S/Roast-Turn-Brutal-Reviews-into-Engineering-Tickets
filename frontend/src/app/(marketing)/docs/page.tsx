"use client";

/**
 * Documentation Page - API Reference & Getting Started
 * ====================================================
 * Comprehensive docs for developers
 */

import { motion } from "framer-motion";
import { Code, FileText, Zap, Shield } from "lucide-react";

const sections = [
  {
    title: "Getting Started",
    icon: Zap,
    content: [
      {
        subtitle: "Quick Start",
        description: "Get up and running in 5 minutes",
        code: `// Install the SDK
npm install @roast/sdk

// Initialize
import { RoastClient } from '@roast/sdk';

const client = new RoastClient({
  apiKey: process.env.ROAST_API_KEY
});

// Upload reviews
const result = await client.reviews.upload({
  file: reviewsFile,
  platform: 'google_play'
});`,
      },
    ],
  },
  {
    title: "Authentication",
    icon: Shield,
    content: [
      {
        subtitle: "API Keys",
        description: "All API requests require authentication via API key",
        code: `curl -X POST https://api.roast.dev/v1/reviews \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"reviews": [...]}'`,
      },
    ],
  },
  {
    title: "CSV Upload API",
    icon: FileText,
    content: [
      {
        subtitle: "Upload Reviews",
        description: "POST endpoint to upload and analyze review data",
        code: `POST /api/bulk/upload

Headers:
  Authorization: Bearer YOUR_API_KEY
  Content-Type: multipart/form-data

Body:
  file: CSV file with reviews
  
Response:
  {
    "upload_id": "uuid",
    "status": "processing",
    "total_reviews": 1500,
    "estimated_time": "2-3 minutes"
  }`,
      },
      {
        subtitle: "Get Upload Status",
        description: "Check processing status of uploaded reviews",
        code: `GET /api/bulk/upload/{upload_id}

Response:
  {
    "upload_id": "uuid",
    "status": "completed",
    "total_reviews": 1500,
    "clusters_created": 23,
    "noise_filtered": 142
  }`,
      },
    ],
  },
  {
    title: "Clusters API",
    icon: Code,
    content: [
      {
        subtitle: "List Clusters",
        description: "Get all clusters for an upload",
        code: `GET /api/bulk/clusters/{upload_id}

Response:
  {
    "clusters": [
      {
        "cluster_id": 1,
        "label": "App Crashes on Launch",
        "summary": "Multiple users reporting...",
        "severity": "critical",
        "review_count": 45,
        "avg_rating": 1.8
      }
    ]
  }`,
      },
      {
        subtitle: "Get Cluster Details",
        description: "Retrieve full details for a specific cluster",
        code: `GET /api/bulk/clusters/{upload_id}/{cluster_id}

Response:
  {
    "cluster_id": 1,
    "label": "App Crashes on Launch",
    "summary": "Users report the app crashes...",
    "severity": "critical",
    "reviews": [
      {
        "text": "App crashes every time...",
        "rating": 1,
        "date": "2024-01-15"
      }
    ]
  }`,
      },
    ],
  },
];

const csvFormat = {
  required: ["text", "rating"],
  optional: ["date", "user_id", "platform"],
  example: `text,rating,date
"Great app! Love the features",5,2024-01-15
"Crashes on startup",1,2024-01-14
"Good but needs improvement",3,2024-01-13`,
};

export default function DocsPage() {
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
              Developer{" "}
              <span className="bg-gradient-to-r from-orange-500 to-red-600 bg-clip-text text-transparent">
                Documentation
              </span>
            </h1>
            <p className="text-lg text-neutral-400 max-w-2xl mx-auto">
              Everything you need to integrate ROAST into your workflow
            </p>
          </motion.div>
        </div>
      </section>

      {/* CSV Format Section */}
      <section className="relative pb-20">
        <div className="max-w-5xl mx-auto px-6">
          <motion.div
            className="bg-neutral-900/50 border border-neutral-800 rounded-2xl p-8"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <h2 className="text-2xl font-bold mb-6 uppercase tracking-wide">CSV Format</h2>
            
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-bold mb-2 text-green-500">Required Columns</h3>
                <ul className="list-disc list-inside text-neutral-300 space-y-1">
                  {csvFormat.required.map((col) => (
                    <li key={col}><code className="text-orange-500">{col}</code> - Review text and rating</li>
                  ))}
                </ul>
              </div>

              <div>
                <h3 className="text-lg font-bold mb-2 text-blue-500">Optional Columns</h3>
                <ul className="list-disc list-inside text-neutral-300 space-y-1">
                  {csvFormat.optional.map((col) => (
                    <li key={col}><code className="text-orange-500">{col}</code> - Additional metadata</li>
                  ))}
                </ul>
              </div>

              <div>
                <h3 className="text-lg font-bold mb-2">Example CSV</h3>
                <pre className="bg-black/50 p-4 rounded-lg overflow-x-auto text-sm border border-neutral-800">
                  <code className="text-neutral-300 font-mono">{csvFormat.example}</code>
                </pre>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* API Documentation Sections */}
      <section className="relative pb-32">
        <div className="max-w-5xl mx-auto px-6 space-y-20">
          {sections.map((section, sectionIndex) => (
            <motion.div
              key={section.title}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: sectionIndex * 0.1 }}
            >
              <div className="flex items-center gap-3 mb-8">
                <section.icon className="w-8 h-8 text-orange-500" />
                <h2 className="text-3xl font-bold">{section.title}</h2>
              </div>

              <div className="space-y-8">
                {section.content.map((item, itemIndex) => (
                  <div
                    key={itemIndex}
                    className="bg-neutral-900/50 border border-neutral-800 rounded-2xl p-8"
                  >
                    <h3 className="text-xl font-bold mb-2">{item.subtitle}</h3>
                    <p className="text-neutral-400 mb-6">{item.description}</p>

                    <pre className="bg-black/50 p-6 rounded-lg overflow-x-auto border border-neutral-800">
                      <code className="text-sm text-neutral-300 font-mono">{item.code}</code>
                    </pre>
                  </div>
                ))}
              </div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Support Section */}
      <section className="relative pb-32">
        <div className="max-w-5xl mx-auto px-6">
          <motion.div
            className="bg-gradient-to-br from-orange-500/10 to-red-600/10 border-2 border-orange-500/50 rounded-2xl p-12 text-center"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <h2 className="text-2xl font-bold mb-4">Need Help?</h2>
            <p className="text-neutral-300 mb-6">
              Our support team is here to help you integrate ROAST
            </p>
            <a
              href="mailto:support@roast.dev"
              className="inline-block px-8 py-3 bg-gradient-to-r from-orange-500 to-red-600 rounded-full font-semibold uppercase tracking-wider text-sm hover:scale-105 transition-transform"
            >
              Contact Support
            </a>
          </motion.div>
        </div>
      </section>
    </div>
  );
}
