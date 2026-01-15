"use client";

/**
 * GlassDock - Floating Glass Sidebar with Active State
 * =====================================================
 * Cyber-Industrial navigation dock with:
 * - Frosted glass morphism effect
 * - Scale + glow animations on hover
 * - Framer Motion layoutId for active indicator
 * - Real active state from pathname
 * 
 * Fixed left-center positioning, z-40
 */

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";

// ============================================================================
// NAVIGATION ITEMS
// ============================================================================

interface NavItem {
  id: string;
  label: string;
  href: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  {
    id: "dashboard",
    label: "Dashboard",
    href: "/dashboard",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
      </svg>
    ),
  },
  {
    id: "clusters",
    label: "Clusters",
    href: "/clusters",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
      </svg>
    ),
  },
  {
    id: "upload",
    label: "Upload",
    href: "/upload",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
      </svg>
    ),
  },
  {
    id: "analytics",
    label: "Analytics",
    href: "/analytics",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
      </svg>
    ),
  },
  {
    id: "settings",
    label: "Settings",
    href: "/settings",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
];

// ============================================================================
// DOCK ITEM COMPONENT
// ============================================================================

interface DockItemProps {
  item: NavItem;
  isActive: boolean;
  isHovered: boolean;
  onHover: (id: string | null) => void;
  onClick: () => void;
}

function DockItem({ item, isActive, isHovered, onHover, onClick }: DockItemProps) {
  return (
    <Link href={item.href} onClick={onClick}>
      <motion.div
        className="relative flex items-center justify-center w-12 h-12 rounded-xl cursor-pointer group"
        onMouseEnter={() => onHover(item.id)}
        onMouseLeave={() => onHover(null)}
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.95 }}
        transition={{ type: "spring", stiffness: 400, damping: 17 }}
      >
        {/* Background glow on hover/active */}
        <AnimatePresence>
          {(isActive || isHovered) && (
            <motion.div
              className="absolute inset-0 rounded-xl bg-gradient-to-br from-orange-500/20 to-red-600/20"
              layoutId="dock-glow"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
            />
          )}
        </AnimatePresence>
        
        {/* Icon */}
        <motion.span
          className={`relative z-10 transition-colors duration-200 ${
            isActive 
              ? "text-orange-500" 
              : isHovered 
                ? "text-white" 
                : "text-neutral-500"
          }`}
        >
          {item.icon}
        </motion.span>
        
        {/* Active indicator dot */}
        <AnimatePresence>
          {isActive && (
            <motion.div
              className="absolute -right-1 w-1.5 h-1.5 rounded-full bg-orange-500"
              layoutId="active-dot"
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0, opacity: 0 }}
              transition={{ type: "spring", stiffness: 500, damping: 30 }}
              style={{
                boxShadow: "0 0 8px rgba(255, 85, 0, 0.8), 0 0 16px rgba(255, 85, 0, 0.4)",
              }}
            />
          )}
        </AnimatePresence>
        
        {/* Tooltip */}
        <AnimatePresence>
          {isHovered && (
            <motion.div
              className="absolute left-full ml-3 px-3 py-1.5 rounded-lg bg-neutral-900/90 border border-white/10 backdrop-blur-sm whitespace-nowrap"
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
              transition={{ duration: 0.15 }}
            >
              <span className="text-sm font-medium text-white">{item.label}</span>
              {/* Tooltip arrow */}
              <div className="absolute left-0 top-1/2 -translate-x-1 -translate-y-1/2 w-2 h-2 rotate-45 bg-neutral-900/90 border-l border-b border-white/10" />
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </Link>
  );
}

// ============================================================================
// GLASS DOCK COMPONENT
// ============================================================================

export function GlassDock() {
  const pathname = usePathname();
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  // Determine active item from pathname
  const getActiveId = () => {
    if (pathname === '/dashboard') return 'dashboard';
    if (pathname === '/upload') return 'upload';
    if (pathname === '/analytics') return 'analytics';
    if (pathname === '/settings') return 'settings';
    if (pathname.startsWith('/clusters')) return 'clusters';
    return 'dashboard';
  };

  const activeId = getActiveId();

  return (
    <motion.nav
      className="fixed left-4 top-1/2 -translate-y-1/2 z-40"
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.5, delay: 0.2 }}
    >
      <div 
        className="flex flex-col items-center gap-2 p-3 rounded-2xl backdrop-blur-2xl bg-black/40 border border-white/10 ring-1 ring-white/5"
        style={{
          boxShadow: `
            inset 0 1px 0 0 rgba(255, 255, 255, 0.05),
            0 10px 40px rgba(0, 0, 0, 0.5)
          `,
        }}
      >
        {/* Logo Icon */}
        <Link href="/dashboard" className="w-12 h-12 flex items-center justify-center mb-2">
          <motion.div 
            className="w-10 h-10 rounded-xl overflow-hidden relative"
            whileHover={{ scale: 1.1, rotate: 5 }}
            whileTap={{ scale: 0.95 }}
            transition={{ type: "spring", stiffness: 400, damping: 17 }}
            style={{
              boxShadow: "0 0 20px rgba(255, 85, 0, 0.4)",
            }}
          >
            <Image 
              src="/logo.png" 
              alt="Roast Logo" 
              width={40} 
              height={40}
              className="object-cover"
            />
          </motion.div>
        </Link>
        
        {/* Divider */}
        <div className="w-8 h-px bg-white/10 mb-2" />
        
        {/* Navigation Items */}
        {navItems.map((item) => (
          <DockItem
            key={item.id}
            item={item}
            isActive={activeId === item.id}
            isHovered={hoveredId === item.id}
            onHover={setHoveredId}
            onClick={() => {}} // Navigation handled by Link
          />
        ))}
      </div>
    </motion.nav>
  );
}

export default GlassDock;
