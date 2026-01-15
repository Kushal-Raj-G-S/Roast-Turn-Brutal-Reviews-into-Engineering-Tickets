/**
 * Auth Layout - Split Screen Design
 * ===================================
 * Dimmed ChaosFluid + Glassmorphism card
 */

import { BackgroundCanvas } from "@/components/background/BackgroundCanvas";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="relative min-h-screen bg-[#030303] flex">
      {/* 3D Background - Dimmed */}
      <div className="fixed inset-0 z-0 opacity-40">
        <BackgroundCanvas />
      </div>

      {/* Noise Texture */}
      <div className="fixed inset-0 z-[1] pointer-events-none opacity-[0.03]">
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
          }}
        />
      </div>

      {/* Content */}
      <div className="relative z-10 flex-1 flex items-center justify-center p-6">
        {children}
      </div>
    </div>
  );
}
