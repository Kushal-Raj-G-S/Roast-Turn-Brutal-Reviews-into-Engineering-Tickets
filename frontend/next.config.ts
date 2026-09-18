import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a self-contained server bundle (.next/standalone) so the production
  // Docker image ships only the traced runtime deps + server.js, not the full
  // node_modules. Keeps the frontend image small and fast to pull/deploy.
  //
  // Deliberately NOT set on Vercel. Vercel runs its own @vercel/nft tracing and
  // expects the default build output; standalone mode doesn't emit the trace
  // files it looks for, so the deploy dies with
  // "ENOENT: ... .next/next-server.js.nft.json". Vercel sets VERCEL=1 during
  // builds, so self-hosted/Docker builds keep standalone and Vercel doesn't.
  output: process.env.VERCEL ? undefined : "standalone",

  reactCompiler: true,

  // Performance optimizations
  experimental: {
    // Optimize package imports
    optimizePackageImports: [
      'framer-motion',
      'lucide-react',
    ],
    
    // Enable parallel route compilation
    webpackBuildWorker: true,
  },
  
  // Faster transpilation
  transpilePackages: ['framer-motion'],
  
  // Image optimization
  images: {
    formats: ['image/webp', 'image/avif'],
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '**',
      },
    ],
  },
  
  // Environment variables for production
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  },
};

export default nextConfig;
