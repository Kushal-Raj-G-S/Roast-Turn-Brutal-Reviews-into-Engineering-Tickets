/**
 * GLSL Shader Definitions for ChaosFluid GPGPU Simulation
 * ========================================================
 * God-Tier Molten Data Lava Effect
 * 
 * These shaders run on GPU for massive parallelism:
 * - Simulation: Physics (curl noise, mouse force, drag)
 * - Render: Visual output (velocity-based sizing, fire colors)
 */

// ============================================================================
// SIMULATION VERTEX SHADER
// Simple passthrough - just render a fullscreen quad
// ============================================================================
export const simulationVertexShader = /* glsl */ `
  varying vec2 vUv;
  
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

// ============================================================================
// SIMULATION FRAGMENT SHADER
// The physics engine - runs per-pixel, each pixel = one particle
// ============================================================================
export const simulationFragmentShader = /* glsl */ `
  uniform sampler2D uPositions;      // Current position texture
  uniform sampler2D uVelocities;     // Current velocity texture
  uniform float uTime;
  uniform float uDeltaTime;
  uniform vec2 uMouse;               // Mouse position in NDC (-1 to 1)
  uniform float uMouseStrength;      // Force multiplier
  uniform vec2 uResolution;
  
  varying vec2 vUv;
  
  // -------------------------------------------------------------------------
  // NOISE FUNCTIONS - Curl Noise for organic fluid motion
  // -------------------------------------------------------------------------
  
  // Classic Perlin-like hash
  vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec4 permute(vec4 x) { return mod289(((x * 34.0) + 1.0) * x); }
  vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }
  
  // 3D Simplex Noise
  float snoise(vec3 v) {
    const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
    
    vec3 i = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);
    
    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);
    
    vec3 x1 = x0 - i1 + C.xxx;
    vec3 x2 = x0 - i2 + C.yyy;
    vec3 x3 = x0 - D.yyy;
    
    i = mod289(i);
    vec4 p = permute(permute(permute(
      i.z + vec4(0.0, i1.z, i2.z, 1.0))
      + i.y + vec4(0.0, i1.y, i2.y, 1.0))
      + i.x + vec4(0.0, i1.x, i2.x, 1.0));
    
    float n_ = 0.142857142857;
    vec3 ns = n_ * D.wyz - D.xzx;
    
    vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
    
    vec4 x_ = floor(j * ns.z);
    vec4 y_ = floor(j - 7.0 * x_);
    
    vec4 x = x_ * ns.x + ns.yyyy;
    vec4 y = y_ * ns.x + ns.yyyy;
    vec4 h = 1.0 - abs(x) - abs(y);
    
    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);
    
    vec4 s0 = floor(b0) * 2.0 + 1.0;
    vec4 s1 = floor(b1) * 2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));
    
    vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
    
    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);
    
    vec4 norm = taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
    p0 *= norm.x;
    p1 *= norm.y;
    p2 *= norm.z;
    p3 *= norm.w;
    
    vec4 m = max(0.6 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
  }
  
  // Curl Noise - creates divergence-free (swirling) motion
  vec3 curlNoise(vec3 p) {
    const float e = 0.1;
    vec3 dx = vec3(e, 0.0, 0.0);
    vec3 dy = vec3(0.0, e, 0.0);
    vec3 dz = vec3(0.0, 0.0, e);
    
    float n1 = snoise(p + dy) - snoise(p - dy);
    float n2 = snoise(p + dz) - snoise(p - dz);
    float n3 = snoise(p + dx) - snoise(p - dx);
    float n4 = snoise(p + dz) - snoise(p - dz);
    float n5 = snoise(p + dx) - snoise(p - dx);
    float n6 = snoise(p + dy) - snoise(p - dy);
    
    return normalize(vec3(n1 - n2, n3 - n4, n5 - n6));
  }
  
  // -------------------------------------------------------------------------
  // MAIN SIMULATION
  // -------------------------------------------------------------------------
  void main() {
    vec4 posData = texture2D(uPositions, vUv);
    vec4 velData = texture2D(uVelocities, vUv);
    
    vec3 position = posData.xyz;
    float life = posData.w;           // Particle life/age
    vec3 velocity = velData.xyz;
    float mass = velData.w;           // Particle mass for force calculation
    
    // Clamp delta time to avoid physics explosion
    float dt = min(uDeltaTime, 0.1);
    
    // -----------------------------------------------------------------------
    // FORCE 1: Curl Noise (organic swirling motion)
    // -----------------------------------------------------------------------
    vec3 noisePos = position * 0.5 + uTime * 0.1;
    vec3 curlForce = curlNoise(noisePos) * 0.3;
    
    // -----------------------------------------------------------------------
    // FORCE 2: Mouse Force Field (explosive push)
    // -----------------------------------------------------------------------
    vec3 mousePos3D = vec3(uMouse * 2.0, 0.0); // Project mouse to 3D
    vec3 toMouse = position - mousePos3D;
    float distToMouse = length(toMouse);
    
    // Radial force - explosive when close
    float mouseRadius = 0.8;
    float mouseInfluence = smoothstep(mouseRadius, 0.0, distToMouse);
    vec3 mouseForce = normalize(toMouse + 0.001) * mouseInfluence * uMouseStrength * 2.0;
    
    // Add some tangential force for swirling around cursor
    vec3 tangent = normalize(cross(toMouse, vec3(0.0, 0.0, 1.0)));
    mouseForce += tangent * mouseInfluence * uMouseStrength * 0.5;
    
    // -----------------------------------------------------------------------
    // FORCE 3: Central Attraction (keeps particles on screen)
    // -----------------------------------------------------------------------
    float distFromCenter = length(position);
    vec3 centerForce = -normalize(position + 0.001) * smoothstep(1.5, 3.0, distFromCenter) * 0.2;
    
    // -----------------------------------------------------------------------
    // FORCE 4: Gravity-like downward pull
    // -----------------------------------------------------------------------
    vec3 gravity = vec3(0.0, -0.02, 0.0);
    
    // -----------------------------------------------------------------------
    // APPLY FORCES
    // -----------------------------------------------------------------------
    vec3 totalForce = curlForce + mouseForce + centerForce + gravity;
    velocity += totalForce * dt / max(mass, 0.1);
    
    // -----------------------------------------------------------------------
    // DRAG (particles slow down)
    // -----------------------------------------------------------------------
    float drag = 0.98;
    velocity *= drag;
    
    // Speed limit to prevent explosion
    float maxSpeed = 3.0;
    float speed = length(velocity);
    if (speed > maxSpeed) {
      velocity = velocity / speed * maxSpeed;
    }
    
    // -----------------------------------------------------------------------
    // UPDATE POSITION
    // -----------------------------------------------------------------------
    position += velocity * dt;
    
    // -----------------------------------------------------------------------
    // BOUNDARY: Respawn particles that go too far
    // -----------------------------------------------------------------------
    if (distFromCenter > 4.0) {
      // Respawn near center with random offset
      float angle = snoise(vec3(vUv * 100.0, uTime)) * 6.28318;
      float radius = 0.5 + abs(snoise(vec3(vUv * 50.0, uTime * 0.5))) * 1.0;
      position = vec3(cos(angle) * radius, sin(angle) * radius, (snoise(vec3(vUv, uTime)) - 0.5) * 0.5);
      velocity *= 0.1;
      life = 0.0;
    }
    
    // Update life
    life += dt;
    
    // Output: position + life in one texture, velocity + mass in another
    // We're outputting position here (velocity handled in separate pass or combined)
    gl_FragColor = vec4(position, life);
  }
`;

// ============================================================================
// VELOCITY SIMULATION FRAGMENT SHADER
// Separate pass for velocity (ping-pong)
// ============================================================================
export const velocityFragmentShader = /* glsl */ `
  uniform sampler2D uPositions;
  uniform sampler2D uVelocities;
  uniform float uTime;
  uniform float uDeltaTime;
  uniform vec2 uMouse;
  uniform float uMouseStrength;
  
  varying vec2 vUv;
  
  // Simplified noise for velocity updates
  float hash(vec3 p) {
    p = fract(p * 0.3183099 + 0.1);
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
  }
  
  void main() {
    vec4 posData = texture2D(uPositions, vUv);
    vec4 velData = texture2D(uVelocities, vUv);
    
    vec3 position = posData.xyz;
    vec3 velocity = velData.xyz;
    float mass = velData.w;
    
    // Mouse force
    vec3 mousePos3D = vec3(uMouse * 2.0, 0.0);
    vec3 toMouse = position - mousePos3D;
    float distToMouse = length(toMouse);
    
    float mouseRadius = 0.8;
    float mouseInfluence = smoothstep(mouseRadius, 0.0, distToMouse);
    vec3 mouseForce = normalize(toMouse + 0.001) * mouseInfluence * uMouseStrength * 3.0;
    
    // Add turbulence
    vec3 turbulence = vec3(
      hash(position * 10.0 + uTime) - 0.5,
      hash(position * 10.0 + uTime + 100.0) - 0.5,
      hash(position * 10.0 + uTime + 200.0) - 0.5
    ) * 0.1;
    
    velocity += (mouseForce + turbulence) * min(uDeltaTime, 0.1);
    velocity *= 0.98; // Drag
    
    gl_FragColor = vec4(velocity, mass);
  }
`;

// ============================================================================
// RENDER VERTEX SHADER
// Transforms particle positions, calculates point size based on velocity
// ============================================================================
export const renderVertexShader = /* glsl */ `
  uniform sampler2D uPositions;
  uniform sampler2D uVelocities;
  uniform float uTime;
  uniform float uPixelRatio;
  uniform float uSize;
  
  varying float vSpeed;
  varying float vLife;
  varying vec3 vColor;
  
  void main() {
    // Get position from simulation texture
    vec4 posData = texture2D(uPositions, position.xy);
    vec4 velData = texture2D(uVelocities, position.xy);
    
    vec3 pos = posData.xyz;
    float life = posData.w;
    vec3 velocity = velData.xyz;
    float speed = length(velocity);
    
    // Pass to fragment
    vSpeed = speed;
    vLife = life;
    
    // Color based on velocity (will be refined in fragment)
    // Dark red at rest, bright orange/white when fast
    float speedNorm = clamp(speed / 2.0, 0.0, 1.0);
    vColor = mix(
      vec3(0.3, 0.05, 0.02),   // Dark ember red
      vec3(1.0, 0.6, 0.1),     // Bright fire orange
      speedNorm
    );
    
    // Add white-hot core for very fast particles
    if (speedNorm > 0.7) {
      vColor = mix(vColor, vec3(1.0, 0.9, 0.7), (speedNorm - 0.7) / 0.3);
    }
    
    // Transform position
    vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
    gl_Position = projectionMatrix * mvPosition;
    
    // Point size: bigger when fast (stretched spark effect)
    float baseSize = uSize;
    float velocityScale = 1.0 + speed * 2.0;
    float distanceScale = 1.0 / -mvPosition.z;
    
    gl_PointSize = baseSize * velocityScale * distanceScale * uPixelRatio * 100.0;
    gl_PointSize = clamp(gl_PointSize, 1.0, 64.0);
  }
`;

// ============================================================================
// RENDER FRAGMENT SHADER
// Creates the fire-like visual with soft glow, additive blending
// ============================================================================
export const renderFragmentShader = /* glsl */ `
  uniform float uTime;
  
  varying float vSpeed;
  varying float vLife;
  varying vec3 vColor;
  
  void main() {
    // Create soft circular particle (no square dots!)
    vec2 center = gl_PointCoord - 0.5;
    float dist = length(center);
    
    // Soft glow falloff
    float alpha = 1.0 - smoothstep(0.0, 0.5, dist);
    alpha *= alpha; // Quadratic falloff for softer glow
    
    // Discard pixels outside circle
    if (alpha < 0.01) discard;
    
    // Color with intensity based on speed
    vec3 color = vColor;
    
    // Add pulsing glow
    float pulse = sin(vLife * 3.0 + vSpeed * 5.0) * 0.1 + 0.9;
    color *= pulse;
    
    // Boost brightness for additive blending
    color *= 1.5;
    
    // Alpha also affected by speed (fast = brighter)
    alpha *= 0.4 + vSpeed * 0.3;
    alpha = clamp(alpha, 0.0, 1.0);
    
    gl_FragColor = vec4(color, alpha);
  }
`;

export default {
  simulationVertexShader,
  simulationFragmentShader,
  velocityFragmentShader,
  renderVertexShader,
  renderFragmentShader,
};
