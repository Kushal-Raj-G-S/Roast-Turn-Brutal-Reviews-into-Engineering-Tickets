"use client";

/**
 * ChaosFluid - God-Tier GPGPU Fluid Simulation
 * =============================================
 * Molten Data Lava: Thousands of particles flowing like liquid fire,
 * leaving trails, reacting violently to mouse like dragging through magma.
 * 
 * Technical Implementation:
 * - GPGPU simulation using FBO ping-pong technique
 * - Curl noise for organic swirling motion
 * - Mouse force field for explosive interaction
 * - Velocity-based particle sizing (fast = stretched sparks)
 * - Additive blending for fire glow effect
 */

import { useRef, useMemo, useEffect } from "react";
import { useFrame, useThree, createPortal } from "@react-three/fiber";
import { useFBO } from "@react-three/drei";
import * as THREE from "three";
import {
  simulationVertexShader,
  simulationFragmentShader,
  renderVertexShader,
  renderFragmentShader,
} from "./shaders";

// ============================================================================
// CONFIGURATION
// ============================================================================

// Simulation resolution (particles = SIZE * SIZE)
const SIM_SIZE = 64; // 64x64 = 4,096 particles
const PARTICLE_COUNT = SIM_SIZE * SIM_SIZE;

// Visual settings
const PARTICLE_SIZE = 0.015;
const MOUSE_STRENGTH = 1.5;

// ============================================================================
// HELPER: Create Data Texture with initial positions
// ============================================================================
function createPositionTexture(size: number): THREE.DataTexture {
  const length = size * size * 4;
  const data = new Float32Array(length);

  for (let i = 0; i < length; i += 4) {
    // Random position in a sphere
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    const radius = 0.5 + Math.random() * 1.5;

    data[i] = radius * Math.sin(phi) * Math.cos(theta);     // x
    data[i + 1] = radius * Math.sin(phi) * Math.sin(theta); // y
    data[i + 2] = (Math.random() - 0.5) * 0.5;              // z (shallow depth)
    data[i + 3] = Math.random() * 10;                        // life/age
  }

  const texture = new THREE.DataTexture(
    data,
    size,
    size,
    THREE.RGBAFormat,
    THREE.FloatType
  );
  texture.needsUpdate = true;
  return texture;
}

function createVelocityTexture(size: number): THREE.DataTexture {
  const length = size * size * 4;
  const data = new Float32Array(length);

  for (let i = 0; i < length; i += 4) {
    // Small random initial velocity
    data[i] = (Math.random() - 0.5) * 0.1;     // vx
    data[i + 1] = (Math.random() - 0.5) * 0.1; // vy
    data[i + 2] = (Math.random() - 0.5) * 0.05; // vz
    data[i + 3] = 0.5 + Math.random() * 0.5;    // mass
  }

  const texture = new THREE.DataTexture(
    data,
    size,
    size,
    THREE.RGBAFormat,
    THREE.FloatType
  );
  texture.needsUpdate = true;
  return texture;
}

// ============================================================================
// SIMULATION MATERIAL (Physics on GPU)
// ============================================================================
class SimulationMaterial extends THREE.ShaderMaterial {
  constructor() {
    super({
      vertexShader: simulationVertexShader,
      fragmentShader: simulationFragmentShader,
      uniforms: {
        uPositions: { value: null },
        uVelocities: { value: null },
        uTime: { value: 0 },
        uDeltaTime: { value: 0.016 },
        uMouse: { value: new THREE.Vector2(0, 0) },
        uMouseStrength: { value: MOUSE_STRENGTH },
        uResolution: { value: new THREE.Vector2(SIM_SIZE, SIM_SIZE) },
      },
    });
  }
}

// ============================================================================
// RENDER MATERIAL (Visuals)
// ============================================================================
class RenderMaterial extends THREE.ShaderMaterial {
  constructor() {
    super({
      vertexShader: renderVertexShader,
      fragmentShader: renderFragmentShader,
      uniforms: {
        uPositions: { value: null },
        uVelocities: { value: null },
        uTime: { value: 0 },
        uPixelRatio: { value: 1 },
        uSize: { value: PARTICLE_SIZE },
      },
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
  }
}

// ============================================================================
// CHAOS FLUID COMPONENT
// ============================================================================
export function ChaosFluid() {
  const { gl, size, viewport } = useThree();

  // Refs
  const simulationMaterialRef = useRef<SimulationMaterial>(null);
  const renderMaterialRef = useRef<RenderMaterial>(null);
  const pointsRef = useRef<THREE.Points>(null);

  // FBO for ping-pong (position simulation)
  const positionFBO1 = useFBO(SIM_SIZE, SIM_SIZE, {
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    format: THREE.RGBAFormat,
    type: THREE.FloatType,
    stencilBuffer: false,
    depthBuffer: false,
  });

  const positionFBO2 = useFBO(SIM_SIZE, SIM_SIZE, {
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    format: THREE.RGBAFormat,
    type: THREE.FloatType,
    stencilBuffer: false,
    depthBuffer: false,
  });

  // Velocity FBOs
  const velocityFBO1 = useFBO(SIM_SIZE, SIM_SIZE, {
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    format: THREE.RGBAFormat,
    type: THREE.FloatType,
    stencilBuffer: false,
    depthBuffer: false,
  });

  const velocityFBO2 = useFBO(SIM_SIZE, SIM_SIZE, {
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    format: THREE.RGBAFormat,
    type: THREE.FloatType,
    stencilBuffer: false,
    depthBuffer: false,
  });

  // Ping-pong state
  const pingPong = useRef(0);
  const initialized = useRef(false);

  // Scene for FBO rendering
  const simScene = useMemo(() => new THREE.Scene(), []);
  const simCamera = useMemo(
    () => new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1),
    []
  );
  const simGeometry = useMemo(() => new THREE.PlaneGeometry(2, 2), []);

  // Initial textures
  const initialPositions = useMemo(() => createPositionTexture(SIM_SIZE), []);
  const initialVelocities = useMemo(() => createVelocityTexture(SIM_SIZE), []);

  // Particle positions (UV coordinates to sample FBO)
  const particlePositions = useMemo(() => {
    const positions = new Float32Array(PARTICLE_COUNT * 3);
    for (let i = 0; i < SIM_SIZE; i++) {
      for (let j = 0; j < SIM_SIZE; j++) {
        const idx = (i * SIM_SIZE + j) * 3;
        positions[idx] = j / (SIM_SIZE - 1);     // u
        positions[idx + 1] = i / (SIM_SIZE - 1); // v
        positions[idx + 2] = 0;
      }
    }
    return positions;
  }, []);

  // Initialize FBOs with data
  useEffect(() => {
    if (initialized.current) return;

    // Create a temporary mesh to render initial data to FBOs
    const initMaterial = new THREE.MeshBasicMaterial({ map: initialPositions });
    const mesh = new THREE.Mesh(simGeometry, initMaterial);
    simScene.add(mesh);

    // Render initial positions
    gl.setRenderTarget(positionFBO1);
    gl.render(simScene, simCamera);
    gl.setRenderTarget(positionFBO2);
    gl.render(simScene, simCamera);

    // Render initial velocities
    initMaterial.map = initialVelocities;
    gl.setRenderTarget(velocityFBO1);
    gl.render(simScene, simCamera);
    gl.setRenderTarget(velocityFBO2);
    gl.render(simScene, simCamera);

    gl.setRenderTarget(null);
    simScene.remove(mesh);
    initMaterial.dispose();

    initialized.current = true;
  }, [gl, simScene, simCamera, simGeometry, initialPositions, initialVelocities, positionFBO1, positionFBO2, velocityFBO1, velocityFBO2]);

  // Simulation material instance
  const simulationMaterial = useMemo(() => new SimulationMaterial(), []);
  const renderMaterial = useMemo(() => new RenderMaterial(), []);

  // Create simulation mesh
  useEffect(() => {
    const mesh = new THREE.Mesh(simGeometry, simulationMaterial);
    simScene.add(mesh);
    return () => {
      simScene.remove(mesh);
    };
  }, [simScene, simGeometry, simulationMaterial]);

  // Animation loop
  useFrame((state, delta) => {
    if (!initialized.current) return;

    const { pointer } = state;
    const time = state.clock.elapsedTime;

    // Determine current and next FBOs (ping-pong)
    const currentPosFBO = pingPong.current === 0 ? positionFBO1 : positionFBO2;
    const nextPosFBO = pingPong.current === 0 ? positionFBO2 : positionFBO1;
    const currentVelFBO = pingPong.current === 0 ? velocityFBO1 : velocityFBO2;
    const nextVelFBO = pingPong.current === 0 ? velocityFBO2 : velocityFBO1;

    // Update simulation uniforms
    simulationMaterial.uniforms.uPositions.value = currentPosFBO.texture;
    simulationMaterial.uniforms.uVelocities.value = currentVelFBO.texture;
    simulationMaterial.uniforms.uTime.value = time;
    simulationMaterial.uniforms.uDeltaTime.value = delta;
    simulationMaterial.uniforms.uMouse.value.set(pointer.x, pointer.y);

    // Run simulation - render to next FBO
    gl.setRenderTarget(nextPosFBO);
    gl.render(simScene, simCamera);
    gl.setRenderTarget(null);

    // Update render material with new positions
    renderMaterial.uniforms.uPositions.value = nextPosFBO.texture;
    renderMaterial.uniforms.uVelocities.value = currentVelFBO.texture;
    renderMaterial.uniforms.uTime.value = time;
    renderMaterial.uniforms.uPixelRatio.value = gl.getPixelRatio();

    // Swap buffers
    pingPong.current = 1 - pingPong.current;
  });

  // Handle resize
  useEffect(() => {
    if (renderMaterial) {
      renderMaterial.uniforms.uPixelRatio.value = gl.getPixelRatio();
    }
  }, [size, gl, renderMaterial]);

  // Create buffer attribute with useMemo to avoid recreation
  const positionAttribute = useMemo(() => {
    return new THREE.BufferAttribute(particlePositions, 3);
  }, [particlePositions]);

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <primitive attach="attributes-position" object={positionAttribute} />
      </bufferGeometry>
      <primitive object={renderMaterial} attach="material" />
    </points>
  );
}

export default ChaosFluid;
