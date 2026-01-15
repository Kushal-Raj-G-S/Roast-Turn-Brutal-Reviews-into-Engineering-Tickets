import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
