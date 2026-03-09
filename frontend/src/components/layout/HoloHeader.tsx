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
import { LogOut, User, Settings, Bell, Search, FileText, Clock } from "lucide-react";

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

interface Notification {
  id: number;
  filename: string;
  status: string;
  created_at: string;
  total_reviews: number;
  clusters_created: number;
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
  const [showNotifications, setShowNotifications] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);
  const notificationRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLDivElement>(null);

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
            console.log('🔍 Fetching plan data...');
            const response = await fetch('/api/proxy/user/plan', {
              headers: {
                'Authorization': `Bearer ${session.session.access_token}`,
                'Content-Type': 'application/json',
              },
            });
            console.log('📡 Plan API response:', response.status, response.statusText);
            if (response.ok) {
              const planData = await response.json();
              console.log('📊 Plan data received:', planData);
              setUserPlan(planData);
            } else {
              const errorText = await response.text();
              console.error('❌ Plan API error:', response.status, errorText);
            }
          } else {
            console.log('⚠️ No auth session for plan fetch');
          }
        } catch (error) {
          console.error('🚨 Plan fetch failed:', error);
        }
      } else {
        setUser(null);
        setUserPlan(null);
      }
    };

    getUser();
  }, []);

  // Fetch notifications (completed uploads)
  useEffect(() => {
    const fetchNotifications = async () => {
      const { data: { user: authUser } } = await supabase.auth.getUser();
      if (!authUser) return;

      const { data } = await supabase
        .from('uploads')
        .select('id, filename, status, created_at, total_reviews, clusters_created')
        .eq('user_id', authUser.id)
        .eq('status', 'completed')
        .order('created_at', { ascending: false })
        .limit(10);

      if (data) {
        setNotifications(data);
      }
    };

    fetchNotifications();

    // Subscribe to new uploads
    const channel = supabase
      .channel('uploads-changes')
      .on('postgres_changes', 
        { event: 'INSERT', schema: 'public', table: 'uploads' },
        () => fetchNotifications()
      )
      .on('postgres_changes', 
        { event: 'UPDATE', schema: 'public', table: 'uploads' },
        () => fetchNotifications()
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDropdown(false);
      }
      if (notificationRef.current && !notificationRef.current.contains(event.target as Node)) {
        setShowNotifications(false);
      }
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setShowSearch(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

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

  // Format relative time for notifications
  const getRelativeTime = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  // Handle search - highlight text across page
  useEffect(() => {
    if (!searchQuery.trim()) {
      // Remove all highlights
      document.querySelectorAll('.search-highlight').forEach(el => {
        const parent = el.parentNode;
        if (parent) {
          parent.replaceChild(document.createTextNode(el.textContent || ''), el);
          parent.normalize();
        }
      });
      return;
    }

    // Simple text highlighting (can be enhanced with better algorithm)
    const highlightText = (node: Node) => {
      if (node.nodeType === Node.TEXT_NODE && node.textContent) {
        const text = node.textContent;
        const regex = new RegExp(`(${searchQuery})`, 'gi');
        if (regex.test(text)) {
          const span = document.createElement('span');
          span.innerHTML = text.replace(regex, '<mark class="search-highlight bg-orange-500/30 text-orange-200 rounded px-0.5">$1</mark>');
          node.parentNode?.replaceChild(span, node);
        }
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        const element = node as Element;
        // Skip script, style, and input elements
        if (!['SCRIPT', 'STYLE', 'INPUT', 'TEXTAREA'].includes(element.tagName)) {
          Array.from(node.childNodes).forEach(highlightText);
        }
      }
    };

    // Clear previous highlights
    document.querySelectorAll('.search-highlight').forEach(el => {
      const parent = el.parentNode;
      if (parent) {
        parent.replaceChild(document.createTextNode(el.textContent || ''), el);
        parent.normalize();
      }
    });

    // Apply new highlights in main content area
    const mainContent = document.querySelector('main');
    if (mainContent) {
      highlightText(mainContent);
    }
  }, [searchQuery]);
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
          
          {/* Enhanced Plan Badge with Smart Usage Display */}
          <div className={`px-2.5 py-1 text-[10px] font-semibold rounded-full border flex items-center gap-2 ${
            userPlan?.plan === 'pro' ? 'text-orange-400 bg-orange-500/20 border-orange-500/50' :
            userPlan?.plan === 'business' ? 'text-purple-400 bg-purple-500/20 border-purple-500/50' :
            userPlan?.plan === 'enterprise' ? 'text-blue-400 bg-blue-500/20 border-blue-500/50' :
            userPlan?.plan === 'starter' ? 'text-green-400 bg-green-500/20 border-green-500/50' :
            'text-neutral-300 bg-neutral-800/80 border-neutral-700'
          }`} style={{ fontFamily: 'var(--font-inter)' }}>
            <span className="uppercase tracking-wide">{userPlan?.label || 'Free'}</span>
            {userPlan && userPlan.uploads_limit && (
              <>
                <div className="w-px h-3 bg-current opacity-40" />
                <span className="font-bold">
                  {userPlan.uploads_used}/{userPlan.uploads_limit}
                </span>
                {/* Smart progress indicator - boxes only for Free plan (≤5), smooth bar for others */}
                {userPlan.uploads_limit <= 5 ? (
                  // Individual boxes for small limits (Free plan) - BIGGER and MORE VISIBLE
                  <div className="flex gap-0.5">
                    {Array.from({ length: userPlan.uploads_limit }, (_, i) => (
                      <div
                        key={i}
                        className={`w-1.5 h-3 rounded-sm transition-all duration-200 ${
                          i < userPlan.uploads_used 
                            ? 'bg-current shadow-sm' 
                            : 'bg-current/25 border border-current/30'
                        }`}
                      />
                    ))}
                  </div>
                ) : (
                  // Smooth progress bar for higher plans - THICKER and MORE VISIBLE
                  <div className="w-6 h-2 bg-current/30 rounded-full overflow-hidden border border-current/40">
                    <div 
                      className="h-full bg-current rounded-full transition-all duration-300 shadow-sm"
                      style={{ 
                        width: `${Math.min((userPlan.uploads_used / userPlan.uploads_limit) * 100, 100)}%` 
                      }}
                    />
                  </div>
                )}
              </>
            )}
            {userPlan && !userPlan.uploads_limit && (
              <>
                <div className="w-px h-3 bg-current opacity-40" />
                <span className="font-bold text-lg">∞</span>
              </>
            )}
          </div>
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
          {/* Search Button with Dropdown */}
          <div className="relative" ref={searchRef}>
            <motion.button
              onClick={() => setShowSearch(!showSearch)}
              className={`p-2 rounded-lg transition-colors ${
                showSearch ? 'text-orange-400 bg-orange-500/10' : 'text-neutral-500 hover:text-white hover:bg-white/5'
              }`}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <Search className="w-5 h-5" />
            </motion.button>

            {/* Search Dropdown */}
            <AnimatePresence>
              {showSearch && (
                <motion.div
                  initial={{ opacity: 0, y: -10, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -10, scale: 0.95 }}
                  transition={{ duration: 0.15 }}
                  className="absolute right-0 mt-2 w-80 rounded-2xl backdrop-blur-xl bg-black/90 border border-white/10 shadow-2xl overflow-hidden z-50"
                  style={{
                    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5), inset 0 1px 0 0 rgba(255, 255, 255, 0.05)'
                  }}
                >
                  <div className="p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Search className="w-4 h-4 text-neutral-500" />
                      <h3 className="text-sm font-semibold text-white">Search</h3>
                    </div>
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Type to highlight text..."
                      className="w-full px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-white placeholder-neutral-500 focus:outline-none focus:border-orange-500/50 focus:ring-1 focus:ring-orange-500/50 transition-all"
                      autoFocus
                    />
                    {searchQuery && (
                      <div className="mt-3 p-2 rounded-lg bg-orange-500/10 border border-orange-500/20">
                        <p className="text-xs text-orange-300">
                          Highlighting &quot;{searchQuery}&quot; across the page
                        </p>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
          
          {/* Notifications with Dropdown */}
          <div className="relative" ref={notificationRef}>
            <motion.button
              onClick={() => setShowNotifications(!showNotifications)}
              className={`relative p-2 rounded-lg transition-colors ${
                showNotifications ? 'text-orange-400 bg-orange-500/10' : 'text-neutral-500 hover:text-white hover:bg-white/5'
              }`}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <Bell className="w-5 h-5" />
              {/* Notification dot */}
              {notifications.length > 0 && (
                <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-orange-500" 
                  style={{ boxShadow: "0 0 6px rgba(255, 85, 0, 0.8)" }}
                />
              )}
            </motion.button>

            {/* Notifications Dropdown */}
            <AnimatePresence>
              {showNotifications && (
                <motion.div
                  initial={{ opacity: 0, y: -10, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -10, scale: 0.95 }}
                  transition={{ duration: 0.15 }}
                  className="absolute right-0 mt-2 w-96 rounded-2xl backdrop-blur-xl bg-black/90 border border-white/10 shadow-2xl overflow-hidden z-50 max-h-[500px] overflow-y-auto"
                  style={{
                    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5), inset 0 1px 0 0 rgba(255, 255, 255, 0.05)'
                  }}
                >
                  {/* Header */}
                  <div className="p-4 border-b border-white/5 sticky top-0 bg-black/90 backdrop-blur-xl">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Bell className="w-4 h-4 text-neutral-400" />
                        <h3 className="text-sm font-semibold text-white">Notifications</h3>
                      </div>
                      {notifications.length > 0 && (
                        <span className="text-xs text-neutral-500">{notifications.length} total</span>
                      )}
                    </div>
                  </div>

                  {/* Notifications List */}
                  <div className="p-2">
                    {notifications.length === 0 ? (
                      <div className="p-8 text-center">
                        <Bell className="w-12 h-12 text-neutral-700 mx-auto mb-3" />
                        <p className="text-sm text-neutral-500">No notifications yet</p>
                        <p className="text-xs text-neutral-600 mt-1">Your completed uploads will appear here</p>
                      </div>
                    ) : (
                      notifications.map((notif) => (
                        <Link
                          key={notif.id}
                          href={`/analytics?upload_id=${notif.id}`}
                          onClick={() => setShowNotifications(false)}
                          className="block p-3 rounded-lg hover:bg-white/5 transition-colors mb-1"
                        >
                          <div className="flex items-start gap-3">
                            <div className="w-10 h-10 rounded-lg bg-green-500/20 border border-green-500/30 flex items-center justify-center flex-shrink-0">
                              <FileText className="w-5 h-5 text-green-400" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-white truncate mb-1">
                                {notif.filename}
                              </p>
                              <div className="flex items-center gap-3 text-xs text-neutral-400">
                                <span>{notif.total_reviews?.toLocaleString()} reviews</span>
                                <span>•</span>
                                <span>{notif.clusters_created} clusters</span>
                              </div>
                              <div className="flex items-center gap-1 mt-1 text-xs text-neutral-500">
                                <Clock className="w-3 h-3" />
                                <span>{getRelativeTime(notif.created_at)}</span>
                              </div>
                            </div>
                          </div>
                        </Link>
                      ))
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
          
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
