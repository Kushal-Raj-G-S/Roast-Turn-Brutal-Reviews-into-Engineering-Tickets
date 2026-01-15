"use client";

/**
 * GridBackground - Cyber-Industrial Background Layer
 * ===================================================
 * Fixed background with:
 * - Radial red glow at bottom center (magma heat effect)
 * - SVG grid pattern with edge fade mask
 * 
 * Sits at z-0, behind all content
 */

export function GridBackground() {
  return (
    <div className="fixed inset-0 z-0 overflow-hidden pointer-events-none">
      {/* Radial Magma Glow - Bottom Center Heat */}
      <div 
        className="absolute inset-0"
        style={{
          background: `
            radial-gradient(
              ellipse 100% 60% at 50% 120%,
              rgba(127, 29, 29, 0.25) 0%,
              rgba(127, 29, 29, 0.1) 30%,
              transparent 70%
            )
          `,
        }}
      />
      
      {/* Secondary Glow - Subtle top corners */}
      <div 
        className="absolute inset-0"
        style={{
          background: `
            radial-gradient(
              ellipse 50% 40% at 0% 0%,
              rgba(255, 46, 0, 0.03) 0%,
              transparent 50%
            ),
            radial-gradient(
              ellipse 50% 40% at 100% 0%,
              rgba(255, 85, 0, 0.02) 0%,
              transparent 50%
            )
          `,
        }}
      />
      
      {/* SVG Grid Pattern with Edge Fade */}
      <div className="absolute inset-0 mask-radial-fade">
        <svg 
          className="w-full h-full opacity-[0.08]"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <pattern 
              id="grid" 
              width="40" 
              height="40" 
              patternUnits="userSpaceOnUse"
            >
              {/* Vertical line */}
              <path 
                d="M 40 0 L 40 40" 
                fill="none" 
                stroke="rgba(255, 255, 255, 0.4)" 
                strokeWidth="0.5"
              />
              {/* Horizontal line */}
              <path 
                d="M 0 40 L 40 40" 
                fill="none" 
                stroke="rgba(255, 255, 255, 0.4)" 
                strokeWidth="0.5"
              />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />
        </svg>
      </div>
      
      {/* Subtle vignette for depth */}
      <div 
        className="absolute inset-0"
        style={{
          background: `
            radial-gradient(
              ellipse 80% 80% at 50% 50%,
              transparent 40%,
              rgba(0, 0, 0, 0.4) 100%
            )
          `,
        }}
      />
    </div>
  );
}

export default GridBackground;
