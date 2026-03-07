"use client";

/**
 * HoloHeader - Floating Holographic Top Bar with User Auth
 * =========================================================
 * Cyber-Industrial header with:
 * - Floating, disconnected from edges (margin-top-4, margin-x-6)
 * - Rounded-full pill shape
 * - Frosted glass morphism
 * - Real user profile from Supabase
 * - User dropdown menu
 * 
 * Fixed top positioning, z-40
 */

import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import Image from "next/image";
import { useEffect, useState, useRef } from "react";
import { supabase } from "@/lib/supabase/client";
import { useRouter, usePathname } from "next/navigation";
import { LogOut, User, Settings } from "lucide-react";

// ============================================================================
// TYPES
// ============================================================================

interface UserProfile {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  provider: string | null;
}

interface UserPlan {
  plan: string;
  label: string;
  uploads_used: number;
  uploads_limit: number | null;
  reviews_limit: number | null;
  reset_date: string;
}

// ============================================================================
// HOLO HEADER COMPONENT
// ============================================================================

export function HoloHeader() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [userPlan, setUserPlan] = useState<UserPlan | null>(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Get current user
    const getUser = async () => {
      const { data: { user: authUser } } = await supabase.auth.getUser();
      
      if (authUser) {
        // Fetch user profile
        const { data: profile } = await supabase
          .from('profiles')
          .select('*')
          .eq('id', authUser.id)
          .single();
        
        if (profile) {
          setUser(profile);
        } else {
          // Fallback to auth metadata
          setUser({
            id: authUser.id,
            email: authUser.email!,
            full_name: authUser.user_metadata?.full_name || null,
            avatar_url: authUser.user_metadata?.avatar_url || null,
            provider: authUser.app_metadata?.provider || null,
          });
        }
        
        // Fetch user plan from backend
        try {
          const { data: session } = await supabase.auth.getSession();
          if (session.session?.access_token) {
            const response = await fetch('/api/proxy/user/plan', {
              headers: {
                'Authorization': `Bearer ${session.session.access_token}`,
                'Content-Type': 'application/json',
              },
            });
            if (response.ok) {
              const planData = await response.json();
              setUserPlan(planData);
            }
          }
        } catch (error) {
          console.log('Could not fetch plan data:', error);
        }
      } else {
        setUser(null);
        setUserPlan(null);
      }
    };

    getUser();
  }, []);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDropdown(false);
      }
    };

    if (showDropdown) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showDropdown]);

  const handleSignOut = async () => {
    await fetch('/api/auth/signout', { method: 'POST' });
    router.push('/');
  };

  // Get current page name from pathname
  const getCurrentPage = () => {
    if (pathname === '/dashboard') return 'Dashboard';
    if (pathname === '/upload') return 'Upload';
    if (pathname === '/analytics') return 'Analytics';
    if (pathname === '/settings') return 'Settings';
    if (pathname.startsWith('/clusters')) return 'Clusters';
    return 'Dashboard';
  };

  // Get user initials
  const getUserInitials = () => {
    if (user?.full_name) {
      return user.full_name
        .split(' ')
        .map(n => n[0])
        .join('')
        .toUpperCase()
        .slice(0, 2);
    }
    return user?.email?.[0]?.toUpperCase() || 'U';
  };

  // Get display name
  const getDisplayName = () => {
    if (user?.full_name) return user.full_name.split(' ')[0];
    return user?.email?.split('@')[0] || 'User';
  };
  return (
    <motion.header
      className="fixed top-4 left-24 right-6 z-40"
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.3 }}
    >
      <div 
        className="flex items-center justify-between px-6 py-3 rounded-full backdrop-blur-md bg-black/20 border border-white/5"
        style={{
          boxShadow: `
            inset 0 1px 0 0 rgba(255, 255, 255, 0.03),
            0 4px 24px rgba(0, 0, 0, 0.3)
          `,
        }}
      >
        {/* Left: Logo */}
        <Link href="/dashboard" className="flex items-center gap-3 group">
          {/* Logo Image */}
          <motion.div 
            className="w-9 h-9 rounded-xl overflow-hidden relative"
            whileHover={{ scale: 1.05 }}
            transition={{ type: "spring", stiffness: 400, damping: 17 }}
            style={{
              boxShadow: "0 0 20px rgba(255, 85, 0, 0.3)",
            }}
          >
            <Image 
              src="/logo.png" 
              alt="Roast Logo" 
              width={36} 
              height={36}
              className="object-cover"
            />
          </motion.div>
          
          {/* Logo Text - Premium Font */}
          <span className="font-bold text-xl tracking-tight bg-gradient-to-r from-orange-500 to-red-600 bg-clip-text text-transparent" style={{ fontFamily: 'var(--font-space)' }}>
            ROAST
          </span>
          
          {/* Plan Badge - replaces version badge */}
          <span className={`px-2 py-0.5 text-[10px] font-medium rounded-full border ${
            userPlan?.plan === 'pro' ? 'text-orange-400 bg-orange-500/10 border-orange-500/30' :
            userPlan?.plan === 'business' ? 'text-purple-400 bg-purple-500/10 border-purple-500/30' :
            userPlan?.plan === 'enterprise' ? 'text-blue-400 bg-blue-500/10 border-blue-500/30' :
            userPlan?.plan === 'starter' ? 'text-green-400 bg-green-500/10 border-green-500/30' :
            'text-neutral-500 bg-neutral-900/50 border-white/5'
          }`} style={{ fontFamily: 'var(--font-inter)' }}>
            {userPlan?.label || 'Free'}
          </span>
        </Link>

        {/* Center: Status / Breadcrumb */}
        <div className="hidden md:flex items-center gap-4">
          {/* Status Indicator */}
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-xs text-neutral-500 font-medium">System Online</span>
          </div>
          
          {/* Separator */}
          <div className="w-px h-4 bg-white/10" />
          
          {/* Current Section */}
          <span className="text-xs text-neutral-400 font-medium">
            {getCurrentPage()}
          </span>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-3">
          {/* Search Button */}
          <motion.button
            className="p-2 rounded-lg text-neutral-500 hover:text-white hover:bg-white/5 transition-colors"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
            </svg>
          </motion.button>
          
          {/* Notifications */}
          <motion.button
            className="relative p-2 rounded-lg text-neutral-500 hover:text-white hover:bg-white/5 transition-colors"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
            </svg>
            {/* Notification dot */}
            <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-orange-500" 
              style={{ boxShadow: "0 0 6px rgba(255, 85, 0, 0.8)" }}
            />
          </motion.button>
          
          {/* Separator */}
          <div className="w-px h-6 bg-white/10" />
          
          {/* User Avatar with Dropdown */}
          <div className="relative" ref={dropdownRef}>
            <motion.button
              onClick={() => setShowDropdown(!showDropdown)}
              className="flex items-center gap-2 p-1 pr-3 rounded-full bg-white/5 hover:bg-white/10 transition-colors"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              {user?.avatar_url ? (
                <img 
                  src={user.avatar_url} 
                  alt={user.full_name || user.email}
                  className="w-7 h-7 rounded-full object-cover"
                />
              ) : (
                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-orange-500 to-red-600 flex items-center justify-center">
                  <span className="text-xs font-bold text-white">{getUserInitials()}</span>
                </div>
              )}
              <span className="text-sm font-medium text-neutral-300">{getDisplayName()}</span>
              <motion.svg 
                className="w-4 h-4 text-neutral-500" 
                fill="none" 
                viewBox="0 0 24 24" 
                stroke="currentColor" 
                strokeWidth={1.5}
                animate={{ rotate: showDropdown ? 180 : 0 }}
                transition={{ duration: 0.2 }}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
              </motion.svg>
            </motion.button>

            {/* Dropdown Menu */}
            <AnimatePresence>
              {showDropdown && (
                <motion.div
                  initial={{ opacity: 0, y: -10, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -10, scale: 0.95 }}
                  transition={{ duration: 0.15 }}
                  className="absolute right-0 mt-2 w-64 rounded-2xl backdrop-blur-xl bg-black/90 border border-white/10 shadow-2xl overflow-hidden z-50"
                  style={{
                    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5), inset 0 1px 0 0 rgba(255, 255, 255, 0.05)'
                  }}
                >
                  {/* User Info Section */}
                  <div className="p-4 border-b border-white/5">
                    <div className="flex items-center gap-3 mb-3">
                      {user?.avatar_url ? (
                        <img 
                          src={user.avatar_url} 
                          alt={user.full_name || user.email}
                          className="w-12 h-12 rounded-full object-cover"
                        />
                      ) : (
                        <div className="w-12 h-12 rounded-full bg-gradient-to-br from-orange-500 to-red-600 flex items-center justify-center">
                          <span className="text-lg font-bold text-white">{getUserInitials()}</span>
                        </div>
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-white truncate">
                          {user?.full_name || 'User'}
                        </p>
                        <p className="text-xs text-neutral-400 truncate">{user?.email}</p>
                      </div>
                    </div>
                    {user?.provider && (
                      <div className="flex items-center gap-2 px-2 py-1 rounded-lg bg-white/5">
                        <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
                        <span className="text-xs text-neutral-400">
                          via {user.provider === 'google' ? 'Google' : user.provider === 'github' ? 'GitHub' : 'Email'}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Menu Items */}
                  <div className="p-2">
                    <Link
                      href="/settings"
                      onClick={() => setShowDropdown(false)}
                      className="flex items-center gap-3 px-3 py-2 rounded-lg text-neutral-300 hover:text-white hover:bg-white/5 transition-colors"
                    >
                      <Settings className="w-4 h-4" />
                      <span className="text-sm font-medium">Settings</span>
                    </Link>
                    
                    <button
                      onClick={() => {
                        setShowDropdown(false);
                        handleSignOut();
                      }}
                      className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-colors"
                    >
                      <LogOut className="w-4 h-4" />
                      <span className="text-sm font-medium">Sign Out</span>
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </motion.header>
  );
}

export default HoloHeader;
