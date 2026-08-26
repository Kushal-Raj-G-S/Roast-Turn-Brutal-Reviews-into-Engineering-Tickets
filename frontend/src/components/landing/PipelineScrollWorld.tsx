"use client";

/**
 * PipelineScrollWorld - Scroll-driven flythrough of Roast's own pipeline
 * ========================================================================
 * Six AI-generated diorama scenes (dark glossy tech miniature, ember-glow,
 * Roast's own orange/red-on-black branding) mapped 1:1 to what the backend
 * actually does to a batch of reviews: Inbox -> Filter -> Constellation ->
 * Tower -> War Room -> Ticket. Scroll position crossfades + Ken-Burns-pans
 * between scenes and drives which scene's copy is pinned on screen.
 *
 * This is the stills-only build of the scroll-world technique (see the
 * `scroll-world` skill) -- no video chain yet (that needs funded Higgsfield/
 * Monid credits). Swapping a scene's still for a real rendered video clip
 * later is a one-line change to SCENES[i].image, nothing else about the
 * scroll mechanics needs to move.
 */

import { useRef, useState, useEffect } from "react";
import { motion, useScroll, useTransform, useMotionValueEvent, useReducedMotion } from "framer-motion";
import { raleway } from "@/fonts/raleway";

interface Scene {
  id: string;
  image: string;
  eyebrow: string;
  title: string;
  body: string;
  accent: string;
}

const SCENES: Scene[] = [
  {
    id: "inbox",
    image: "/scroll-world/scene-1.webp",
    eyebrow: "Step 1 — Ingest",
    title: "Thousands of reviews. No signal.",
    accent: "#a3a3a3",
    body: "Every review lands here first — star ratings, free text, noise and signal all mixed together.",
  },
  {
    id: "filter",
    image: "/scroll-world/scene-2.webp",
    eyebrow: "Step 2 — Noise filter",
    title: "The noise drops away in seconds.",
    accent: "#fb923c",
    body: "Generic praise, spam, and near-duplicate reviews are filtered out before any AI touches the data.",
  },
  {
    id: "constellation",
    image: "/scroll-world/scene-3.webp",
    eyebrow: "Step 3 — Semantic clustering",
    title: "Similar issues, however they're worded.",
    accent: "#f97316",
    body: "“Crashes on login” and “freezes when signing in” land in the same cluster — matched by meaning, not keywords.",
  },
  {
    id: "tower",
    image: "/scroll-world/scene-4.webp",
    eyebrow: "Step 4 — Severity",
    title: "Ranked by what actually matters.",
    accent: "#dc2626",
    body: "Every cluster is classified CRITICAL through LOW, automatically, based on impact and volume.",
  },
  {
    id: "warroom",
    image: "/scroll-world/scene-5.webp",
    eyebrow: "Step 5 — Agentic RCA",
    title: "An AI that checks its own work.",
    accent: "#f97316",
    body: "A multi-step agent hypothesizes a root cause, checks past resolved issues, critiques itself, then finalizes a report.",
  },
  {
    id: "ticket",
    image: "/scroll-world/scene-6.webp",
    eyebrow: "Step 6 — Ship it",
    title: "Turn brutal reviews into engineering tickets.",
    accent: "#f97316",
    body: "A structured, ready-to-file ticket — root cause, repro steps, suggested fix — exported straight to GitHub or Linear.",
  },
];

const N = SCENES.length;
// Each scene's opacity is a trapezoid over a continuous "which scene am I
// closest to" position, not a hand-rolled set of per-scene keyframe arrays.
// The earlier approach (four fade points per scene, math'd differently at
// the first/last index to dodge keyframe collisions) was fragile in
// practice: it produced a scene stuck fully visible at the wrong time and
// another (the finale) bleeding into its neighbor's band. A single closed-
// form function of "distance from my index" can't collide with anything --
// there's nothing to special-case, index 0 and index N-1 fall out of the
// same formula as every scene in between.
const PLATEAU = 0.15; // stay fully opaque within this many "scene widths" of center
const FALLOFF = 0.55; // then linearly fade out over this many more
const HALF_WIDTH = PLATEAU + FALLOFF;

function SceneLayer({
  scene,
  index,
  scenePosition,
}: {
  scene: Scene;
  index: number;
  scenePosition: import("framer-motion").MotionValue<number>;
}) {
  // A trapezoid centered on this scene's own index, expressed as a plain
  // 4-point array transform (the standard, always-supported useTransform
  // signature) instead of a custom per-value function -- these keyframes
  // are just `index` offset by fixed constants, never clamped against a
  // shared boundary, so unlike the original per-scene math there's nothing
  // for index 0 or index N-1 to collide with.
  const opacity = useTransform(
    scenePosition,
    [index - HALF_WIDTH, index - PLATEAU, index + PLATEAU, index + HALF_WIDTH],
    [0, 1, 1, 0]
  );
  // Gentle Ken Burns push-in across this same window.
  const scale = useTransform(scenePosition, [index - HALF_WIDTH, index + HALF_WIDTH], [1.0, 1.07]);

  return (
    <motion.div
      className="absolute inset-0"
      style={{ opacity }}
      aria-hidden={index !== 0}
    >
      <motion.img
        src={scene.image}
        alt={scene.title}
        className="absolute inset-0 w-full h-full object-cover"
        // These stills were art-directed as small floating dioramas on a
        // near-black background (fine at thumbnail size) but stretched
        // full-bleed as a hero background they read as almost entirely
        // black. Lift brightness/contrast/saturation so the actual scene
        // is visible instead of looking like nothing rendered.
        style={{ scale, filter: "brightness(1.65) contrast(1.15) saturate(1.2)" }}
        // All 6 scenes occupy the exact same position:absolute box (only
        // opacity differs), so native `loading="lazy"` can't tell them
        // apart by viewport distance -- it silently never fired for one of
        // them, leaving an earlier scene's image stuck visible underneath.
        // These are ~six small webp files; just load them all eagerly.
        loading="eager"
        draggable={false}
      />
      {/* Only darken near the very bottom (behind the pinned copy) --
          the old full-frame gradient stacked on top of an already-dark
          image was making the whole scene unreadable. */}
      <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/5 to-transparent" />
    </motion.div>
  );
}

export function PipelineScrollWorld() {
  const containerRef = useRef<HTMLDivElement>(null);
  const prefersReducedMotion = useReducedMotion();
  const [activeIndex, setActiveIndex] = useState(0);

  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start start", "end end"],
  });
  // Continuous 0..N-1 "which scene" position -- the single source of truth
  // SceneLayer's opacity/scale and the active-index-driven copy both read
  // from, so the pinned text and the visible background can't disagree.
  const scenePosition = useTransform(scrollYProgress, [0, 1], [0, N - 1]);

  useMotionValueEvent(scrollYProgress, "change", (v) => {
    const idx = Math.min(N - 1, Math.max(0, Math.floor(v * N)));
    setActiveIndex((prev) => (prev !== idx ? idx : prev));
  });

  const active = SCENES[activeIndex];

  // Reduced-motion: skip the scroll-jacked pin entirely, just show each
  // scene as a normal in-flow fade-in-on-view section.
  if (prefersReducedMotion) {
    return (
      <div className={`relative bg-neutral-950 ${raleway.variable}`} style={{ fontFamily: "var(--font-raleway-scroll)" }}>
        {SCENES.map((scene, i) => (
          <motion.section
            key={scene.id}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 0.5 }}
            className="relative flex flex-col items-center justify-center gap-6 py-24 px-6 text-center"
          >
            <img
              src={scene.image}
              alt={scene.title}
              className="w-full max-w-2xl rounded-2xl border border-white/10"
              style={{ filter: "brightness(1.65) contrast(1.15) saturate(1.2)" }}
            />
            <div className="max-w-xl">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] mb-2" style={{ color: scene.accent }}>
                {scene.eyebrow}
              </p>
              <h3 className="font-extrabold text-2xl md:text-4xl text-white mb-3 tracking-wide">{scene.title}</h3>
              <p className="text-neutral-400">{scene.body}</p>
            </div>
          </motion.section>
        ))}
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`relative ${raleway.variable}`}
      style={{ height: `${N * 170}vh` }}
    >
      <div className="sticky top-0 h-screen w-full overflow-hidden bg-neutral-950">
        {SCENES.map((scene, i) => (
          <SceneLayer key={scene.id} scene={scene} index={i} scenePosition={scenePosition} />
        ))}

        {/* Pinned copy, bottom-left, crossfades with the active scene */}
        <div className="absolute inset-x-0 bottom-0 z-10 px-6 pb-6 md:px-16 md:pb-10">
          <motion.div
            key={active.id}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="max-w-xl"
            style={{ fontFamily: "var(--font-raleway-scroll)" }}
          >
            <p
              className="text-xs font-semibold uppercase tracking-[0.2em] mb-3"
              style={{ color: active.accent }}
            >
              {active.eyebrow}
            </p>
            <h3 className="font-extrabold text-3xl md:text-6xl text-white mb-4 leading-[1.05] tracking-wide drop-shadow-[0_4px_24px_rgba(0,0,0,0.6)]">
              {active.title}
            </h3>
            <p className="text-base md:text-lg text-neutral-300 max-w-lg">{active.body}</p>
          </motion.div>
        </div>

        {/* Route rail */}
        <div className="absolute right-6 top-1/2 -translate-y-1/2 z-10 hidden md:flex flex-col gap-3">
          {SCENES.map((scene, i) => (
            <div
              key={scene.id}
              className="w-2 h-2 rounded-full transition-all duration-300"
              style={{
                backgroundColor: i === activeIndex ? active.accent : "rgba(255,255,255,0.2)",
                transform: i === activeIndex ? "scale(1.5)" : "scale(1)",
              }}
              title={scene.title}
            />
          ))}
        </div>

        {/* Scroll hint, only on the first scene */}
        {activeIndex === 0 && (
          <motion.div
            className="absolute bottom-8 right-6 md:right-16 z-10 text-xs text-neutral-500 tracking-widest uppercase"
            animate={{ opacity: [0.4, 1, 0.4] }}
            transition={{ duration: 2, repeat: Infinity }}
          >
            Scroll ↓
          </motion.div>
        )}
      </div>
    </div>
  );
}
