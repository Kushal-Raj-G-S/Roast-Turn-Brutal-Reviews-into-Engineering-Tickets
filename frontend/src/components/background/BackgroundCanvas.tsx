"use client";

/**
 * BackgroundCanvas - R3F Scene Wrapper
 * =====================================
 * Sets up the Three.js scene with camera, lights, and dark background.
 * Renders ChaosFluid GPGPU particle simulation behind app content.
 * 
 * Visual: Molten Data Lava - liquid fire flowing with mouse interaction
 * 
 * Usage:
 *   <BackgroundCanvas /> // Place in layout, sits behind content via z-index
 */

import { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { Preload } from "@react-three/drei";
import { ChaosFluid } from "./ChaosFluid";

// ============================================================================
// BACKGROUND CANVAS COMPONENT
// ============================================================================

export function BackgroundCanvas() {
  return (
    <div className="fixed inset-0 -z-10" aria-hidden="true">
      <Canvas
        // Camera setup: positioned to view the fluid simulation
        camera={{
          position: [0, 0, 3],
          fov: 75,
          near: 0.01,
          far: 100,
        }}
        // Performance optimizations
        dpr={[1, 2]} // Clamp pixel ratio for perf
        gl={{
          antialias: false, // Disable for particle performance
          alpha: false, // Opaque background for perf
          powerPreference: "high-performance",
          preserveDrawingBuffer: false,
        }}
        // Dark background color
        style={{ background: "#050505" }}
      >
        {/* Scene background color - deeper black for fire contrast */}
        <color attach="background" args={["#050505"]} />
        
        {/* No lights needed - particles are self-illuminating with additive blending */}
        
        {/* Suspense boundary for async loading */}
        <Suspense fallback={null}>
          <ChaosFluid />
          <Preload all />
        </Suspense>
      </Canvas>
    </div>
  );
}

export default BackgroundCanvas;
