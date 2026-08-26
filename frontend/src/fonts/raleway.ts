import localFont from "next/font/local";

// Scoped to PipelineScrollWorld only -- not added to the global font stack
// in layout.tsx on purpose (the rest of the site keeps its existing fonts).
export const raleway = localFont({
  src: [
    { path: "./raleway/Raleway-Medium.ttf", weight: "500", style: "normal" },
    { path: "./raleway/Raleway-SemiBold.ttf", weight: "600", style: "normal" },
    { path: "./raleway/Raleway-ExtraBold.ttf", weight: "800", style: "normal" },
  ],
  variable: "--font-raleway-scroll",
  display: "swap",
});
