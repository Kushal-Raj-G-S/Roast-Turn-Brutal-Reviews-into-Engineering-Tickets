import type { Metadata } from "next";
import { Familjen_Grotesk, Smooch_Sans, Azeret_Mono, Black_Ops_One, Space_Grotesk, Inter, Playfair_Display } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import { Preloader } from "@/components/ui/Preloader";
import { CursorGlow } from "@/components/ui/CursorGlow";

// Wild premium font stack - ultra-modern, edgy, different
const familjen = Familjen_Grotesk({
  variable: "--font-familjen",
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

const smooch = Smooch_Sans({
  variable: "--font-smooch",
  subsets: ["latin"],
  display: "swap",
  weight: ["100", "200", "300", "400", "500", "600", "700", "800", "900"],
});

const azeret = Azeret_Mono({
  variable: "--font-azeret",
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700", "800", "900"],
});

const blackOps = Black_Ops_One({
  variable: "--font-blackops",
  subsets: ["latin"],
  display: "swap",
  weight: "400",
});

const spaceGrotesk = Space_Grotesk({
  variable: "--font-space",
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700", "800"],
});

// Premium display font for headlines
const playfair = Playfair_Display({
  variable: "--font-playfair",
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "700", "900"],
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: "Roast | Turn Brutal Reviews into Engineering Tickets",
  description: "AI-powered SaaS that transforms user complaints into actionable engineering tickets",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${familjen.variable} ${smooch.variable} ${azeret.variable} ${blackOps.variable} ${spaceGrotesk.variable} ${inter.variable} ${playfair.variable} antialiased min-h-screen overflow-x-hidden`}
      >
        <Preloader />
        <CursorGlow />
        <ThemeProvider>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
