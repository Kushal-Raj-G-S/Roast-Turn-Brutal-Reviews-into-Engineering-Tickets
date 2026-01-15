"use client";

/**
 * ChaosField - High-Performance 3D Particle System
 * =================================================
 * A dark sci-fi / data visualization aesthetic particle field.
 * 
 * Features:
 * - 3,000 particles rendered in a single draw call (BufferGeometry)
 * - Noise-based swirling vortex animation
 * - Mouse-reactive repulsion effect
 * - Additive blending for glow overlap
 * - 60fps performance optimized
 */

import { useRef, useMemo } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";

// ============================================================================
// CONSTANTS
// ============================================================================

const PARTICLE_COUNT = 3000;
const PARTICLE_SIZE = 0.02;
const OPACITY = 0.6;

// Colors: Roast Red → Fire Orange gradient
const COLOR_RED = new THREE.Color("#ff4444");
const COLOR_ORANGE = new THREE.Color("#ff8800");

// Animation params
const VORTEX_SPEED = 0.15;
const NOISE_SCALE = 0.8;
const REPULSION_RADIUS = 0.3;
const REPULSION_STRENGTH = 0.015;

// ============================================================================
// NOISE FUNCTIONS (Simplex-like for smooth organic motion)
// ============================================================================

/**
 * Simple 3D noise function for vortex motion.
 * Using sin/cos combination for smooth, deterministic noise.
 */
function noise3D(x: number, y: number, z: number, time: number): number {
  const n1 = Math.sin(x * 1.5 + time * 0.3) * Math.cos(y * 1.2 + time * 0.2);
  const n2 = Math.sin(y * 1.8 + time * 0.25) * Math.cos(z * 1.4 + time * 0.35);
  const n3 = Math.sin(z * 1.3 + time * 0.28) * Math.cos(x * 1.6 + time * 0.22);
  return (n1 + n2 + n3) / 3;
}

/**
 * Get vortex displacement for a particle position.
 * Creates a swirling, organic motion pattern.
 */
function getVortexDisplacement(
  x: number,
  y: number,
  z: number,
  time: number
): THREE.Vector3 {
  const nx = noise3D(x * NOISE_SCALE, y * NOISE_SCALE, z * NOISE_SCALE, time);
  const ny = noise3D(
    y * NOISE_SCALE + 100,
    z * NOISE_SCALE,
    x * NOISE_SCALE,
    time + 50
  );
  const nz = noise3D(
    z * NOISE_SCALE + 200,
    x * NOISE_SCALE,
    y * NOISE_SCALE,
    time + 100
  );

  return new THREE.Vector3(
    nx * VORTEX_SPEED * 0.01,
    ny * VORTEX_SPEED * 0.01,
    nz * VORTEX_SPEED * 0.008
  );
}

// ============================================================================
// CHAOS FIELD COMPONENT
// ============================================================================

export function ChaosField() {
  // Refs for direct buffer manipulation (no React re-renders)
  const pointsRef = useRef<THREE.Points>(null);
  const originalPositions = useRef<Float32Array | null>(null);

  // Access Three.js state for mouse tracking
  const { pointer } = useThree();

  // -------------------------------------------------------------------------
  // MEMOIZED: Initial particle positions (random sphere distribution)
  // -------------------------------------------------------------------------
  const { positions, colors } = useMemo(() => {
    const pos = new Float32Array(PARTICLE_COUNT * 3);
    const col = new Float32Array(PARTICLE_COUNT * 3);

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const i3 = i * 3;

      // Spherical distribution for organic look
      const radius = 1.5 + Math.random() * 1.5; // 1.5 to 3.0 radius
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);

      pos[i3] = radius * Math.sin(phi) * Math.cos(theta);
      pos[i3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
      pos[i3 + 2] = radius * Math.cos(phi);

      // Color gradient: Red → Orange based on distance from center
      const t = Math.random();
      const color = COLOR_RED.clone().lerp(COLOR_ORANGE, t);
      col[i3] = color.r;
      col[i3 + 1] = color.g;
      col[i3 + 2] = color.b;
    }

    return { positions: pos, colors: col };
  }, []);

  // Store original positions for animation reset
  useMemo(() => {
    originalPositions.current = positions.slice();
  }, [positions]);

  // -------------------------------------------------------------------------
  // ANIMATION LOOP (useFrame for 60fps)
  // -------------------------------------------------------------------------
  useFrame((state) => {
    if (!pointsRef.current || !originalPositions.current) return;

    const geometry = pointsRef.current.geometry;
    const positionAttribute = geometry.getAttribute(
      "position"
    ) as THREE.BufferAttribute;
    const posArray = positionAttribute.array as Float32Array;
    const origArray = originalPositions.current;

    const time = state.clock.elapsedTime;

    // Mouse position in 3D space (projected onto z=0 plane, scaled)
    const mouseX = pointer.x * 2;
    const mouseY = pointer.y * 2;

    // Update each particle
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const i3 = i * 3;

      // Get original position
      const ox = origArray[i3];
      const oy = origArray[i3 + 1];
      const oz = origArray[i3 + 2];

      // Calculate vortex displacement
      const vortex = getVortexDisplacement(ox, oy, oz, time);

      // Apply vortex motion
      let nx = ox + vortex.x * time;
      let ny = oy + vortex.y * time;
      let nz = oz + vortex.z * time;

      // Slowly rotate in spiral
      const angle = time * 0.05 + i * 0.001;
      const rotatedX = nx * Math.cos(angle) - nz * Math.sin(angle);
      const rotatedZ = nx * Math.sin(angle) + nz * Math.cos(angle);
      nx = rotatedX;
      nz = rotatedZ;

      // Mouse repulsion effect
      const dx = nx - mouseX;
      const dy = ny - mouseY;
      const distSq = dx * dx + dy * dy;

      if (distSq < REPULSION_RADIUS * REPULSION_RADIUS && distSq > 0.0001) {
        const dist = Math.sqrt(distSq);
        const force = (1 - dist / REPULSION_RADIUS) * REPULSION_STRENGTH;
        nx += (dx / dist) * force;
        ny += (dy / dist) * force;
      }

      // Update buffer
      posArray[i3] = nx;
      posArray[i3 + 1] = ny;
      posArray[i3 + 2] = nz;
    }

    // Mark buffer as needing update
    positionAttribute.needsUpdate = true;

    // Slow rotation of the entire particle system
    pointsRef.current.rotation.y += 0.0003;
    pointsRef.current.rotation.x += 0.0001;
  });

  // -------------------------------------------------------------------------
  // RENDER
  // -------------------------------------------------------------------------
  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
        />
        <bufferAttribute
          attach="attributes-color"
          args={[colors, 3]}
        />
      </bufferGeometry>
      <pointsMaterial
        size={PARTICLE_SIZE}
        vertexColors
        transparent
        opacity={OPACITY}
        blending={THREE.AdditiveBlending}
        depthWrite={false}
        sizeAttenuation
      />
    </points>
  );
}

export default ChaosField;
