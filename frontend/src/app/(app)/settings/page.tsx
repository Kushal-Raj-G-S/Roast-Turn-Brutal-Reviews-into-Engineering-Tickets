"use client";

/**
 * Settings Page - User Preferences
 * =================================
 * Account settings, theme toggle, and preferences
 */

import { motion } from "framer-motion";
import { User, Bell, Shield, Moon, Sun, Mail, Lock, Globe, Zap, ChevronRight, Webhook, Check, Loader2 } from "lucide-react";
import { SpotlightCard } from "@/components/ui";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase/client";
import { apiClient } from "@/lib/api-client";

export default function SettingsPage() {
  const [user, setUser] = useState<any>(null);
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [notifications, setNotifications] = useState({
    email: true,
    push: false,
    weekly: true,
  });

  // Proactive alerting — Slack/Discord webhook, wired to the real backend
  // (see /settings/alerts). Not tied to the mock notification toggles above.
  const [webhookUrl, setWebhookUrl] = useState("");
  const [alertsEnabled, setAlertsEnabled] = useState(true);
  const [webhookStatus, setWebhookStatus] = useState<"idle" | "loading" | "saving" | "testing" | "saved" | "tested" | "error">("idle");
  const [webhookError, setWebhookError] = useState<string | null>(null);

  useEffect(() => {
    // Get current user
    const getUser = async () => {
      const { data: { user: authUser } } = await supabase.auth.getUser();
      if (authUser) {
        const { data: profile } = await supabase
          .from('profiles')
          .select('*')
          .eq('id', authUser.id)
          .single();
        
        setUser(profile || {
          email: authUser.email,
          full_name: authUser.user_metadata?.full_name,
          avatar_url: authUser.user_metadata?.avatar_url,
        });
      }
    };
    getUser();

    // Load theme from localStorage
    const savedTheme = localStorage.getItem('theme') as 'dark' | 'light' || 'dark';
    setTheme(savedTheme);

    // Apply theme on mount
    if (savedTheme === 'light') {
      document.documentElement.classList.add('light-theme');
    }

    // Load current alert webhook settings
    setWebhookStatus("loading");
    ensureFreshToken()
      .then(() => apiClient.getAlertSettings())
      .then((s) => {
        setWebhookUrl(s.alert_webhook_url || "");
        setAlertsEnabled(s.alerts_enabled);
        setWebhookStatus("idle");
      })
      .catch(() => setWebhookStatus("idle"));
  }, []);

  // apiClient falls back to a token cached in localStorage from whatever
  // session last called setToken() -- fine for pages that already fetch a
  // fresh Supabase session before every call (e.g. analytics.tsx), but this
  // page didn't, so it was silently reusing a long-expired token and every
  // request 401'd with "token is expired". getSession() refreshes if needed.
  const ensureFreshToken = async () => {
    const { data: { session } } = await supabase.auth.getSession();
    if (session?.access_token) apiClient.setToken(session.access_token);
  };

  const saveWebhook = async () => {
    setWebhookStatus("saving");
    setWebhookError(null);
    try {
      await ensureFreshToken();
      await apiClient.updateAlertSettings({ alert_webhook_url: webhookUrl || null, alerts_enabled: alertsEnabled });
      setWebhookStatus("saved");
      setTimeout(() => setWebhookStatus("idle"), 2000);
    } catch (e: any) {
      setWebhookStatus("error");
      setWebhookError(e.message || "Failed to save");
    }
  };

  const testWebhook = async () => {
    setWebhookStatus("testing");
    setWebhookError(null);
    try {
      await ensureFreshToken();
      await apiClient.testAlertWebhook();
      setWebhookStatus("tested");
      setTimeout(() => setWebhookStatus("idle"), 2500);
    } catch (e: any) {
      setWebhookStatus("error");
      setWebhookError(e.message || "Test failed — check the URL");
    }
  };

  const toggleTheme = () => {
    const newTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
    localStorage.setItem('theme', newTheme);
    
    // Apply theme to document
    if (newTheme === 'light') {
      document.documentElement.classList.add('light-theme');
      console.log('✨ Switched to Light Theme');
    } else {
      document.documentElement.classList.remove('light-theme');
      console.log('🌙 Switched to Dark Theme');
    }
  };

  const setThemeMode = (mode: 'dark' | 'light') => {
    setTheme(mode);
    localStorage.setItem('theme', mode);
    
    if (mode === 'light') {
      document.documentElement.classList.add('light-theme');
      console.log('✨ Switched to Light Theme');
    } else {
      document.documentElement.classList.remove('light-theme');
      console.log('🌙 Switched to Dark Theme');
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-neutral-500">Manage your account and preferences</p>
      </motion.div>

      {/* Settings Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Profile Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <SpotlightCard className="p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500/20 to-red-500/20 border border-orange-500/20 flex items-center justify-center">
                <User className="w-5 h-5 text-orange-400" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-white">Profile</h3>
                <p className="text-xs text-neutral-500">Manage your account information</p>
              </div>
            </div>

            <div className="space-y-4">
              <div>
                <label className="text-xs text-neutral-500 mb-2 block">Email</label>
                <div className="flex items-center gap-3 p-3 rounded-xl bg-white/5 border border-white/10">
                  <Mail className="w-4 h-4 text-neutral-500" />
                  <span className="text-sm text-white">{user?.email || 'Loading...'}</span>
                </div>
              </div>

              <div>
                <label className="text-xs text-neutral-500 mb-2 block">Full Name</label>
                <div className="flex items-center gap-3 p-3 rounded-xl bg-white/5 border border-white/10">
                  <User className="w-4 h-4 text-neutral-500" />
                  <span className="text-sm text-white">{user?.full_name || 'Not set'}</span>
                </div>
              </div>

              <button className="w-full flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/10 text-neutral-300 hover:bg-white/10 transition-colors">
                <div className="flex items-center gap-3">
                  <Lock className="w-4 h-4" />
                  <span className="text-sm">Change Password</span>
                </div>
                <ChevronRight className="w-4 h-4 text-neutral-500" />
              </button>
            </div>
          </SpotlightCard>
        </motion.div>

        {/* Appearance Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <SpotlightCard className="p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 border border-purple-500/20 flex items-center justify-center">
                {theme === 'dark' ? (
                  <Moon className="w-5 h-5 text-purple-400" />
                ) : (
                  <Sun className="w-5 h-5 text-purple-400" />
                )}
              </div>
              <div>
                <h3 className="text-lg font-bold text-white">Appearance</h3>
                <p className="text-xs text-neutral-500">Customize your visual experience</p>
              </div>
            </div>

            <div className="space-y-4">
              {/* Theme Toggle */}
              <div>
                <label className="text-xs text-neutral-500 mb-3 block">Theme</label>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setThemeMode('dark')}
                    className={`flex-1 flex items-center justify-center gap-2 p-3 rounded-xl border transition-all ${
                      theme === 'dark'
                        ? 'bg-white/10 border-white/20 text-white'
                        : 'bg-white/5 border-white/10 text-neutral-500'
                    }`}
                  >
                    <Moon className="w-4 h-4" />
                    <span className="text-sm font-medium">Dark</span>
                  </button>
                  <button
                    onClick={() => setThemeMode('light')}
                    className={`flex-1 flex items-center justify-center gap-2 p-3 rounded-xl border transition-all ${
                      theme === 'light'
                        ? 'bg-white/10 border-white/20 text-white'
                        : 'bg-white/5 border-white/10 text-neutral-500'
                    }`}
                  >
                    <Sun className="w-4 h-4" />
                    <span className="text-sm font-medium">Light</span>
                  </button>
                </div>
                <p className="text-xs text-neutral-600 mt-2">
                  {theme === 'dark' ? 'Currently using dark mode' : 'Currently using light mode'}
                </p>
              </div>

              {/* Language */}
              <div>
                <label className="text-xs text-neutral-500 mb-2 block">Language</label>
                <button className="w-full flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/10 text-neutral-300 hover:bg-white/10 transition-colors">
                  <div className="flex items-center gap-3">
                    <Globe className="w-4 h-4" />
                    <span className="text-sm">English (US)</span>
                  </div>
                  <ChevronRight className="w-4 h-4 text-neutral-500" />
                </button>
              </div>
            </div>
          </SpotlightCard>
        </motion.div>

        {/* Notifications Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <SpotlightCard className="p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500/20 to-cyan-500/20 border border-blue-500/20 flex items-center justify-center">
                <Bell className="w-5 h-5 text-blue-400" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-white">Notifications</h3>
                <p className="text-xs text-neutral-500">Control how you receive updates</p>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/10">
                <div className="flex items-center gap-3">
                  <Mail className="w-4 h-4 text-neutral-500" />
                  <div>
                    <p className="text-sm text-white">Email Notifications</p>
                    <p className="text-xs text-neutral-500">Get updates via email</p>
                  </div>
                </div>
                <button
                  onClick={() => setNotifications(prev => ({ ...prev, email: !prev.email }))}
                  className={`w-12 h-6 rounded-full transition-colors ${
                    notifications.email ? 'bg-orange-500' : 'bg-neutral-700'
                  }`}
                >
                  <div
                    className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      notifications.email ? 'translate-x-6' : 'translate-x-0.5'
                    }`}
                  />
                </button>
              </div>

              <div className="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/10">
                <div className="flex items-center gap-3">
                  <Bell className="w-4 h-4 text-neutral-500" />
                  <div>
                    <p className="text-sm text-white">Push Notifications</p>
                    <p className="text-xs text-neutral-500">Get browser alerts</p>
                  </div>
                </div>
                <button
                  onClick={() => setNotifications(prev => ({ ...prev, push: !prev.push }))}
                  className={`w-12 h-6 rounded-full transition-colors ${
                    notifications.push ? 'bg-orange-500' : 'bg-neutral-700'
                  }`}
                >
                  <div
                    className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      notifications.push ? 'translate-x-6' : 'translate-x-0.5'
                    }`}
                  />
                </button>
              </div>

              <div className="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/10">
                <div className="flex items-center gap-3">
                  <Zap className="w-4 h-4 text-neutral-500" />
                  <div>
                    <p className="text-sm text-white">Weekly Digest</p>
                    <p className="text-xs text-neutral-500">Summary every Monday</p>
                  </div>
                </div>
                <button
                  onClick={() => setNotifications(prev => ({ ...prev, weekly: !prev.weekly }))}
                  className={`w-12 h-6 rounded-full transition-colors ${
                    notifications.weekly ? 'bg-orange-500' : 'bg-neutral-700'
                  }`}
                >
                  <div
                    className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      notifications.weekly ? 'translate-x-6' : 'translate-x-0.5'
                    }`}
                  />
                </button>
              </div>
            </div>
          </SpotlightCard>
        </motion.div>

        {/* Proactive Alerts Section — real backend wiring (Slack/Discord webhook) */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35 }}
        >
          <SpotlightCard className="p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500/20 to-red-500/20 border border-orange-500/20 flex items-center justify-center">
                <Webhook className="w-5 h-5 text-orange-400" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-white">Proactive Alerts</h3>
                <p className="text-xs text-neutral-500">Get pinged in Slack/Discord the moment something needs attention</p>
              </div>
            </div>

            <div className="space-y-4">
              <div>
                <label className="text-xs text-neutral-500 mb-2 block">Webhook URL</label>
                <input
                  type="text"
                  value={webhookUrl}
                  onChange={(e) => setWebhookUrl(e.target.value)}
                  placeholder="https://hooks.slack.com/services/... or https://discord.com/api/webhooks/..."
                  className="w-full p-3 rounded-xl bg-white/5 border border-white/10 text-sm text-white placeholder:text-neutral-600 focus:outline-none focus:border-orange-500/50"
                />
                <p className="text-xs text-neutral-600 mt-2">
                  Paste a Slack incoming-webhook or Discord webhook URL. Fires when a fix doesn't hold (a resolved
                  cluster resurfaces) or a new CRITICAL cluster is created — free to set up on Slack/Discord's own side.
                </p>
              </div>

              <div className="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/10">
                <div className="flex items-center gap-3">
                  <Bell className="w-4 h-4 text-neutral-500" />
                  <div>
                    <p className="text-sm text-white">Alerts Enabled</p>
                    <p className="text-xs text-neutral-500">Toggle off to pause without losing the URL</p>
                  </div>
                </div>
                <button
                  onClick={() => setAlertsEnabled((v) => !v)}
                  className={`w-12 h-6 rounded-full transition-colors ${alertsEnabled ? 'bg-orange-500' : 'bg-neutral-700'}`}
                >
                  <div className={`w-5 h-5 bg-white rounded-full transition-transform ${alertsEnabled ? 'translate-x-6' : 'translate-x-0.5'}`} />
                </button>
              </div>

              {webhookError && (
                <p className="text-xs text-red-400">{webhookError}</p>
              )}

              <div className="flex items-center gap-3">
                <button
                  onClick={saveWebhook}
                  disabled={webhookStatus === "saving" || webhookStatus === "testing"}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-orange-500 to-red-600 text-white text-sm font-semibold hover:shadow-lg hover:shadow-orange-500/25 transition-all disabled:opacity-50"
                >
                  {webhookStatus === "saving" ? <Loader2 className="w-4 h-4 animate-spin" /> : webhookStatus === "saved" ? <Check className="w-4 h-4" /> : null}
                  {webhookStatus === "saved" ? "Saved" : "Save"}
                </button>
                <button
                  onClick={testWebhook}
                  disabled={!webhookUrl || webhookStatus === "saving" || webhookStatus === "testing"}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-white/5 border border-white/10 text-neutral-200 text-sm font-medium hover:bg-white/10 transition-colors disabled:opacity-40"
                >
                  {webhookStatus === "testing" ? <Loader2 className="w-4 h-4 animate-spin" /> : webhookStatus === "tested" ? <Check className="w-4 h-4 text-emerald-400" /> : null}
                  {webhookStatus === "tested" ? "Sent!" : "Send test alert"}
                </button>
              </div>
            </div>
          </SpotlightCard>
        </motion.div>

        {/* Security Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
        >
          <SpotlightCard className="p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-green-500/20 to-emerald-500/20 border border-green-500/20 flex items-center justify-center">
                <Shield className="w-5 h-5 text-green-400" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-white">Security</h3>
                <p className="text-xs text-neutral-500">Protect your account</p>
              </div>
            </div>

            <div className="space-y-3">
              <button className="w-full flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/10 text-neutral-300 hover:bg-white/10 transition-colors">
                <div className="flex items-center gap-3">
                  <Lock className="w-4 h-4" />
                  <div className="text-left">
                    <p className="text-sm text-white">Two-Factor Auth</p>
                    <p className="text-xs text-neutral-500">Add extra security</p>
                  </div>
                </div>
                <span className="text-xs text-orange-400 font-medium">Setup</span>
              </button>

              <button className="w-full flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/10 text-neutral-300 hover:bg-white/10 transition-colors">
                <div className="flex items-center gap-3">
                  <Shield className="w-4 h-4" />
                  <div className="text-left">
                    <p className="text-sm text-white">Active Sessions</p>
                    <p className="text-xs text-neutral-500">Manage logged-in devices</p>
                  </div>
                </div>
                <ChevronRight className="w-4 h-4 text-neutral-500" />
              </button>

              <button className="w-full flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/10 text-neutral-300 hover:bg-white/10 transition-colors">
                <div className="flex items-center gap-3">
                  <Lock className="w-4 h-4" />
                  <div className="text-left">
                    <p className="text-sm text-white">Privacy Settings</p>
                    <p className="text-xs text-neutral-500">Control your data</p>
                  </div>
                </div>
                <ChevronRight className="w-4 h-4 text-neutral-500" />
              </button>
            </div>
          </SpotlightCard>
        </motion.div>
      </div>

      {/* Save Changes Button */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
        className="flex justify-end"
      >
        <button className="px-8 py-3 rounded-xl bg-gradient-to-r from-orange-500 to-red-600 text-white font-semibold hover:shadow-lg hover:shadow-orange-500/25 transition-all">
          Save Changes
        </button>
      </motion.div>
    </div>
  );
}
