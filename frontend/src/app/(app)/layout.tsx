/**
 * App Layout - Dragon UI Wrapper
 * ================================
 * GlassDock sidebar + HoloHeader + ChaosFluid background
 */

import { BackgroundCanvas } from "@/components/background/BackgroundCanvas";
import { GridBackground } from "@/components/layout/GridBackground";
import { GlassDock } from "@/components/layout/GlassDock";
import { HoloHeader } from "@/components/layout/HoloHeader";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="relative min-h-screen bg-[#030303]">
      {/* 3D Background - Fixed, slightly dimmed for readability */}
      <div className="fixed inset-0 z-0 opacity-60">
        <BackgroundCanvas />
      </div>

      {/* Grid Overlay */}
      <GridBackground />

      {/* Noise Texture */}
      <div className="fixed inset-0 z-[1] pointer-events-none opacity-[0.03]">
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
          }}
        />
      </div>

      {/* Floating Glass Dock - Left Side */}
      <GlassDock />

      {/* Holographic Header - Top */}
      <HoloHeader />

      {/* Main Content Area */}
      <main className="relative z-10 pl-24 pt-20 pr-6 pb-6 min-h-screen">
        {children}
      </main>
    </div>
  );
}
