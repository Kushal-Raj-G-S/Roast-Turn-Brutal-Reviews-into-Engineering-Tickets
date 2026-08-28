"use client";

/**
 * Settings Page - User Preferences
 * =================================
 * Account settings, theme toggle, and preferences
 */

import { motion, AnimatePresence } from "framer-motion";
import { User, Bell, Shield, Moon, Sun, Mail, Lock, Globe, Zap, ChevronRight, Webhook, Check, Loader2, ShieldCheck, ShieldOff, Copy, X, AlertCircle, Send } from "lucide-react";
import { SpotlightCard } from "@/components/ui";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase/client";
import { apiClient } from "@/lib/api-client";
import { isPushSupported, getExistingSubscription, subscribeToPush, unsubscribeFromPush } from "@/lib/push";

interface MfaFactor {
  id: string;
  friendly_name?: string;
  status: string;
}

interface ActiveSession {
  id: string;
  created_at: string | null;
  updated_at: string | null;
  not_after: string | null;
  user_agent: string | null;
  ip: string | null;
  is_current: boolean;
}

/** Rough, best-effort "Chrome on Windows" from a raw User-Agent string --
 * good enough for a device list, not meant to be a real UA parser. */
function describeUserAgent(ua: string | null): string {
  if (!ua) return "Unknown device";
  const isMobile = /Mobile|Android|iPhone/i.test(ua);
  let browser = "Unknown browser";
  if (/Edg\//.test(ua)) browser = "Edge";
  else if (/Chrome\//.test(ua)) browser = "Chrome";
  else if (/Firefox\//.test(ua)) browser = "Firefox";
  else if (/Safari\//.test(ua)) browser = "Safari";
  let os = "Unknown OS";
  if (/Windows/.test(ua)) os = "Windows";
  else if (/Mac OS X/.test(ua)) os = "macOS";
  else if (/Android/.test(ua)) os = "Android";
  else if (/iPhone|iPad/.test(ua)) os = "iOS";
  else if (/Linux/.test(ua)) os = "Linux";
  return `${browser} on ${os}${isMobile ? " (mobile)" : ""}`;
}

export default function SettingsPage() {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  // Email notifications + weekly digest -- real, persisted via the same
  // /settings/alerts endpoint as the webhook (own independent flags,
  // email_alerts_enabled / weekly_digest_enabled), not local-only state.
  const [emailAlertsEnabled, setEmailAlertsEnabled] = useState(true);
  const [weeklyDigestEnabled, setWeeklyDigestEnabled] = useState(true);
  const [emailTestStatus, setEmailTestStatus] = useState<"idle" | "testing" | "tested" | "error">("idle");
  const [emailTestError, setEmailTestError] = useState<string | null>(null);

  // Push notifications -- real Web Push (self-hosted VAPID, see lib/push.ts),
  // not a mock toggle. "subscribed" reflects THIS browser's actual service
  // worker subscription state, checked on mount rather than assumed.
  const [pushSupported, setPushSupported] = useState(true);
  const [pushSubscribed, setPushSubscribed] = useState(false);
  const [pushStatus, setPushStatus] = useState<"idle" | "subscribing" | "unsubscribing" | "testing" | "error">("idle");
  const [pushError, setPushError] = useState<string | null>(null);

  // Proactive alerting — Slack/Discord webhook, wired to the real backend
  // (see /settings/alerts). Not tied to the mock notification toggles above.
  const [webhookUrl, setWebhookUrl] = useState("");
  const [alertsEnabled, setAlertsEnabled] = useState(true);
  const [webhookStatus, setWebhookStatus] = useState<"idle" | "loading" | "saving" | "testing" | "saved" | "tested" | "error">("idle");
  const [webhookError, setWebhookError] = useState<string | null>(null);

  // Change password -- real Supabase Auth, no backend of our own needed.
  // Re-authenticating with the current password first (rather than just
  // calling updateUser directly) confirms it's actually the account owner
  // making a sensitive change, since an active session alone doesn't ask
  // for anything the user knows.
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordStatus, setPasswordStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [passwordError, setPasswordError] = useState<string | null>(null);

  // Two-factor auth -- real Supabase Auth MFA (TOTP). The actual
  // enforcement (does a login really get challenged) lives in proxy.ts,
  // not here -- this is just enroll/verify/unenroll.
  const [mfaFactors, setMfaFactors] = useState<MfaFactor[]>([]);
  const [mfaLoading, setMfaLoading] = useState(true);
  const [enrolling, setEnrolling] = useState(false);
  const [enrollFactorId, setEnrollFactorId] = useState<string | null>(null);
  const [qrCode, setQrCode] = useState<string | null>(null);
  const [totpSecret, setTotpSecret] = useState<string | null>(null);
  const [verifyCode, setVerifyCode] = useState("");
  const [mfaStatus, setMfaStatus] = useState<"idle" | "enrolling" | "verifying" | "unenrolling" | "error">("idle");
  const [mfaError, setMfaError] = useState<string | null>(null);

  const verifiedFactor = mfaFactors.find((f) => f.status === "verified");

  // Active sessions -- real rows from Supabase's own auth.sessions table
  // (GET /account/sessions), not a mocked device list.
  const [showSessions, setShowSessions] = useState(false);
  const [sessions, setSessions] = useState<ActiveSession[]>([]);
  const [sessionsStatus, setSessionsStatus] = useState<"idle" | "loading" | "revoking" | "error">("idle");
  const [sessionsError, setSessionsError] = useState<string | null>(null);

  // Privacy -- real data export (GET /account/export) and real account
  // deletion (DELETE /account), gated behind a typed confirmation since
  // there's no undo once it runs.
  const [showPrivacy, setShowPrivacy] = useState(false);
  const [exportStatus, setExportStatus] = useState<"idle" | "exporting" | "error">("idle");
  const [exportError, setExportError] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [deleteStatus, setDeleteStatus] = useState<"idle" | "deleting" | "error">("idle");
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const loadMfaFactors = async () => {
    const { data, error } = await supabase.auth.mfa.listFactors();
    if (!error && data) {
      setMfaFactors((data.totp || []) as MfaFactor[]);
    }
    setMfaLoading(false);
  };

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
    loadMfaFactors();

    setPushSupported(isPushSupported());
    if (isPushSupported()) {
      getExistingSubscription().then((sub) => setPushSubscribed(!!sub));
    }

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
        setEmailAlertsEnabled(s.email_alerts_enabled);
        setWeeklyDigestEnabled(s.weekly_digest_enabled);
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

  const toggleEmailAlerts = async () => {
    const next = !emailAlertsEnabled;
    setEmailAlertsEnabled(next); // optimistic -- a settings toggle should feel instant
    try {
      await ensureFreshToken();
      await apiClient.updateAlertSettings({ email_alerts_enabled: next });
    } catch {
      setEmailAlertsEnabled(!next); // revert -- the flip looked like it worked but the save failed
    }
  };

  const toggleWeeklyDigest = async () => {
    const next = !weeklyDigestEnabled;
    setWeeklyDigestEnabled(next);
    try {
      await ensureFreshToken();
      await apiClient.updateAlertSettings({ weekly_digest_enabled: next });
    } catch {
      setWeeklyDigestEnabled(!next);
    }
  };

  const testEmailAlert = async () => {
    setEmailTestStatus("testing");
    setEmailTestError(null);
    try {
      await ensureFreshToken();
      await apiClient.testAlertEmail();
      setEmailTestStatus("tested");
      setTimeout(() => setEmailTestStatus("idle"), 2500);
    } catch (e: any) {
      setEmailTestStatus("error");
      setEmailTestError(e.message || "Test email failed");
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

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError(null);

    if (newPassword.length < 6) {
      setPasswordError("New password must be at least 6 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError("New passwords don't match.");
      return;
    }

    setPasswordStatus("saving");
    try {
      // Confirms the current password is actually correct before allowing
      // the change -- an active session alone doesn't prove the person at
      // the keyboard right now knows the existing password.
      const { error: signInError } = await supabase.auth.signInWithPassword({
        email: user?.email,
        password: currentPassword,
      });
      if (signInError) throw new Error("Current password is incorrect.");

      const { error: updateError } = await supabase.auth.updateUser({ password: newPassword });
      if (updateError) throw updateError;

      setPasswordStatus("saved");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setTimeout(() => {
        setPasswordStatus("idle");
        setShowPasswordForm(false);
      }, 1500);
    } catch (e: any) {
      setPasswordStatus("error");
      setPasswordError(e.message || "Failed to change password");
    }
  };

  const startMfaEnroll = async () => {
    setMfaStatus("enrolling");
    setMfaError(null);
    try {
      const { data, error } = await supabase.auth.mfa.enroll({
        factorType: "totp",
        friendlyName: `Authenticator (${new Date().toISOString().slice(0, 10)})`,
      });
      if (error) throw error;
      setEnrollFactorId(data.id);
      setQrCode(data.totp.qr_code);
      setTotpSecret(data.totp.secret);
      setEnrolling(true);
      setMfaStatus("idle");
    } catch (e: any) {
      setMfaStatus("error");
      setMfaError(e.message || "Couldn't start 2FA setup");
    }
  };

  const cancelMfaEnroll = async () => {
    // Supabase leaves an "unverified" factor behind if enrollment is
    // abandoned -- clean it up rather than leaving a dangling half-set-up
    // factor that would otherwise clutter (or block) a future attempt.
    if (enrollFactorId) {
      await supabase.auth.mfa.unenroll({ factorId: enrollFactorId });
    }
    setEnrolling(false);
    setEnrollFactorId(null);
    setQrCode(null);
    setTotpSecret(null);
    setVerifyCode("");
    setMfaError(null);
  };

  const confirmMfaEnroll = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!enrollFactorId) return;
    setMfaStatus("verifying");
    setMfaError(null);
    try {
      const { data: challenge, error: challengeError } = await supabase.auth.mfa.challenge({
        factorId: enrollFactorId,
      });
      if (challengeError) throw challengeError;

      const { error: verifyError } = await supabase.auth.mfa.verify({
        factorId: enrollFactorId,
        challengeId: challenge.id,
        code: verifyCode.trim(),
      });
      if (verifyError) throw verifyError;

      setEnrolling(false);
      setEnrollFactorId(null);
      setQrCode(null);
      setTotpSecret(null);
      setVerifyCode("");
      setMfaStatus("idle");
      await loadMfaFactors();
    } catch (e: any) {
      setMfaStatus("error");
      setMfaError(e.message || "That code didn't match — try again.");
    }
  };

  const disableMfa = async () => {
    if (!verifiedFactor) return;
    if (!window.confirm("Turn off two-factor authentication? You'll only need your password to sign in.")) return;
    setMfaStatus("unenrolling");
    setMfaError(null);
    try {
      const { error } = await supabase.auth.mfa.unenroll({ factorId: verifiedFactor.id });
      if (error) throw error;
      setMfaStatus("idle");
      await loadMfaFactors();
    } catch (e: any) {
      setMfaStatus("error");
      setMfaError(e.message || "Failed to disable 2FA");
    }
  };

  const enablePush = async () => {
    setPushStatus("subscribing");
    setPushError(null);
    try {
      await ensureFreshToken();
      const sub = await subscribeToPush();
      await apiClient.subscribePush(sub.toJSON() as any);
      setPushSubscribed(true);
      setPushStatus("idle");
    } catch (e: any) {
      setPushStatus("error");
      setPushError(e.message || "Couldn't enable push notifications");
    }
  };

  const disablePush = async () => {
    setPushStatus("unsubscribing");
    setPushError(null);
    try {
      const endpoint = await unsubscribeFromPush();
      if (endpoint) {
        await ensureFreshToken();
        await apiClient.unsubscribePush(endpoint);
      }
      setPushSubscribed(false);
      setPushStatus("idle");
    } catch (e: any) {
      setPushStatus("error");
      setPushError(e.message || "Couldn't disable push notifications");
    }
  };

  const testPush = async () => {
    setPushStatus("testing");
    setPushError(null);
    try {
      await ensureFreshToken();
      await apiClient.testPush();
      setPushStatus("idle");
    } catch (e: any) {
      setPushStatus("error");
      setPushError(e.message || "Test push failed");
    }
  };

  const loadSessions = async () => {
    setSessionsStatus("loading");
    setSessionsError(null);
    try {
      await ensureFreshToken();
      const list = await apiClient.getActiveSessions();
      setSessions(list);
      setSessionsStatus("idle");
    } catch (e: any) {
      setSessionsStatus("error");
      setSessionsError(e.message || "Failed to load active sessions");
    }
  };

  const toggleSessions = () => {
    const next = !showSessions;
    setShowSessions(next);
    if (next && sessions.length === 0) loadSessions();
  };

  const revokeOtherSessions = async () => {
    if (!window.confirm("Sign out every other device? This device stays signed in.")) return;
    setSessionsStatus("revoking");
    setSessionsError(null);
    try {
      const { error } = await supabase.auth.signOut({ scope: "others" });
      if (error) throw error;
      await loadSessions();
    } catch (e: any) {
      setSessionsStatus("error");
      setSessionsError(e.message || "Failed to sign out other devices");
    }
  };

  const togglePrivacy = () => setShowPrivacy((v) => !v);

  const exportData = async () => {
    setExportStatus("exporting");
    setExportError(null);
    try {
      await ensureFreshToken();
      const data = await apiClient.exportAccountData();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `roast-data-export-${Date.now()}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      setExportStatus("idle");
    } catch (e: any) {
      setExportStatus("error");
      setExportError(e.message || "Failed to export your data");
    }
  };

  const confirmDeleteAccount = async () => {
    if (deleteConfirmText !== "DELETE") return;
    setDeleteStatus("deleting");
    setDeleteError(null);
    try {
      await ensureFreshToken();
      await apiClient.deleteAccount();
      await supabase.auth.signOut();
      router.push("/login");
    } catch (e: any) {
      setDeleteStatus("error");
      setDeleteError(e.message || "Failed to delete your account");
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

              <button
                onClick={() => setShowPasswordForm((v) => !v)}
                className="w-full flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/10 text-neutral-300 hover:bg-white/10 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <Lock className="w-4 h-4" />
                  <span className="text-sm">Change Password</span>
                </div>
                <ChevronRight className={`w-4 h-4 text-neutral-500 transition-transform ${showPasswordForm ? "rotate-90" : ""}`} />
              </button>

              <AnimatePresence>
                {showPasswordForm && (
                  <motion.form
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    onSubmit={handleChangePassword}
                    className="overflow-hidden space-y-3"
                  >
                    <input
                      type="password"
                      value={currentPassword}
                      onChange={(e) => setCurrentPassword(e.target.value)}
                      placeholder="Current password"
                      required
                      className="w-full p-3 rounded-xl bg-white/5 border border-white/10 text-sm text-white placeholder:text-neutral-600 focus:outline-none focus:border-orange-500/50"
                    />
                    <input
                      type="password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="New password (min 6 characters)"
                      required
                      className="w-full p-3 rounded-xl bg-white/5 border border-white/10 text-sm text-white placeholder:text-neutral-600 focus:outline-none focus:border-orange-500/50"
                    />
                    <input
                      type="password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="Confirm new password"
                      required
                      className="w-full p-3 rounded-xl bg-white/5 border border-white/10 text-sm text-white placeholder:text-neutral-600 focus:outline-none focus:border-orange-500/50"
                    />
                    {passwordError && <p className="text-xs text-red-400">{passwordError}</p>}
                    <button
                      type="submit"
                      disabled={passwordStatus === "saving"}
                      className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-orange-500 to-red-600 text-white text-sm font-semibold hover:shadow-lg hover:shadow-orange-500/25 transition-all disabled:opacity-50"
                    >
                      {passwordStatus === "saving" ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : passwordStatus === "saved" ? (
                        <Check className="w-4 h-4" />
                      ) : null}
                      {passwordStatus === "saved" ? "Password updated" : "Update password"}
                    </button>
                  </motion.form>
                )}
              </AnimatePresence>
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
              {/* Real, persisted via /settings/alerts (email_alerts_enabled) --
                  fires for the same events as the Discord/push alerts. */}
              <div className="p-3 rounded-xl bg-white/5 border border-white/10">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Mail className="w-4 h-4 text-neutral-500" />
                    <div>
                      <p className="text-sm text-white">Email Notifications</p>
                      <p className="text-xs text-neutral-500">Get an email on new critical issues or a fix that didn't hold</p>
                    </div>
                  </div>
                  <button
                    onClick={toggleEmailAlerts}
                    className={`w-12 h-6 rounded-full transition-colors ${
                      emailAlertsEnabled ? 'bg-orange-500' : 'bg-neutral-700'
                    }`}
                  >
                    <div
                      className={`w-5 h-5 bg-white rounded-full transition-transform ${
                        emailAlertsEnabled ? 'translate-x-6' : 'translate-x-0.5'
                      }`}
                    />
                  </button>
                </div>
                {emailTestError && <p className="text-xs text-red-400 mt-2">{emailTestError}</p>}
                {emailAlertsEnabled && (
                  <button
                    onClick={testEmailAlert}
                    disabled={emailTestStatus === "testing"}
                    className="mt-3 flex items-center gap-1.5 text-xs text-neutral-400 hover:text-neutral-200 disabled:opacity-50"
                  >
                    {emailTestStatus === "testing" ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : emailTestStatus === "tested" ? (
                      <Check className="w-3 h-3 text-emerald-400" />
                    ) : (
                      <Send className="w-3 h-3" />
                    )}
                    {emailTestStatus === "testing" ? "Sending…" : emailTestStatus === "tested" ? "Sent!" : "Send test email"}
                  </button>
                )}
              </div>

              {/* Real Web Push -- self-hosted VAPID, no third-party service.
                  Reflects THIS browser's actual subscription state rather
                  than a mock preference. */}
              <div className="p-3 rounded-xl bg-white/5 border border-white/10">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Bell className="w-4 h-4 text-neutral-500" />
                    <div>
                      <p className="text-sm text-white">Push Notifications</p>
                      <p className="text-xs text-neutral-500">
                        {!pushSupported
                          ? "Not supported in this browser"
                          : pushSubscribed
                          ? "Enabled on this browser"
                          : "Get a browser alert on new critical issues or a fix that didn't hold"}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => (pushSubscribed ? disablePush() : enablePush())}
                    disabled={!pushSupported || pushStatus === "subscribing" || pushStatus === "unsubscribing"}
                    className={`w-12 h-6 rounded-full transition-colors disabled:opacity-40 ${
                      pushSubscribed ? "bg-orange-500" : "bg-neutral-700"
                    }`}
                  >
                    <div
                      className={`w-5 h-5 bg-white rounded-full transition-transform flex items-center justify-center ${
                        pushSubscribed ? "translate-x-6" : "translate-x-0.5"
                      }`}
                    >
                      {(pushStatus === "subscribing" || pushStatus === "unsubscribing") && (
                        <Loader2 className="w-3 h-3 animate-spin text-neutral-500" />
                      )}
                    </div>
                  </button>
                </div>
                {pushError && <p className="text-xs text-red-400 mt-2">{pushError}</p>}
                {pushSubscribed && (
                  <button
                    onClick={testPush}
                    disabled={pushStatus === "testing"}
                    className="mt-3 flex items-center gap-1.5 text-xs text-neutral-400 hover:text-neutral-200 disabled:opacity-50"
                  >
                    {pushStatus === "testing" ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
                    {pushStatus === "testing" ? "Sending…" : "Send test notification"}
                  </button>
                )}
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
                  onClick={toggleWeeklyDigest}
                  className={`w-12 h-6 rounded-full transition-colors ${
                    weeklyDigestEnabled ? 'bg-orange-500' : 'bg-neutral-700'
                  }`}
                >
                  <div
                    className={`w-5 h-5 bg-white rounded-full transition-transform ${
                      weeklyDigestEnabled ? 'translate-x-6' : 'translate-x-0.5'
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
              {/* Two-Factor Auth -- real Supabase Auth MFA (TOTP), enforced
                  server-side in proxy.ts (redirects to /verify-2fa on the
                  next sign-in), not just a UI toggle. */}
              <div className="p-3 rounded-xl bg-white/5 border border-white/10">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {verifiedFactor ? (
                      <ShieldCheck className="w-4 h-4 text-emerald-400" />
                    ) : (
                      <Lock className="w-4 h-4" />
                    )}
                    <div className="text-left">
                      <p className="text-sm text-white">Two-Factor Auth</p>
                      <p className="text-xs text-neutral-500">
                        {mfaLoading
                          ? "Checking…"
                          : verifiedFactor
                          ? "Enabled — you'll be asked for a code on your next sign-in"
                          : "Add an authenticator-app code at sign-in"}
                      </p>
                    </div>
                  </div>
                  {!mfaLoading && !verifiedFactor && !enrolling && (
                    <button
                      onClick={startMfaEnroll}
                      disabled={mfaStatus === "enrolling"}
                      className="text-xs text-orange-400 font-medium hover:text-orange-300 disabled:opacity-50"
                    >
                      {mfaStatus === "enrolling" ? "Starting…" : "Set up"}
                    </button>
                  )}
                  {!mfaLoading && verifiedFactor && (
                    <button
                      onClick={disableMfa}
                      disabled={mfaStatus === "unenrolling"}
                      className="flex items-center gap-1 text-xs text-red-400 font-medium hover:text-red-300 disabled:opacity-50"
                    >
                      <ShieldOff className="w-3.5 h-3.5" />
                      {mfaStatus === "unenrolling" ? "Disabling…" : "Disable"}
                    </button>
                  )}
                </div>

                {mfaError && <p className="text-xs text-red-400 mt-2">{mfaError}</p>}

                <AnimatePresence>
                  {enrolling && qrCode && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="overflow-hidden mt-4 pt-4 border-t border-white/10"
                    >
                      <p className="text-xs text-neutral-400 mb-3">
                        Scan this with Google Authenticator, Authy, or any TOTP app — then enter the 6-digit code it shows.
                      </p>
                      <div className="flex flex-col items-center gap-3">
                        {/* eslint-disable-next-line @next/next/no-img-element -- data: URI, not an optimizable asset */}
                        <img src={qrCode} alt="2FA QR code" className="w-40 h-40 rounded-lg bg-white p-2" />
                        {totpSecret && (
                          <button
                            onClick={() => navigator.clipboard.writeText(totpSecret)}
                            className="flex items-center gap-1.5 text-xs text-neutral-400 hover:text-neutral-200 font-mono"
                            title="Copy manual-entry secret"
                          >
                            <Copy className="w-3 h-3" />
                            {totpSecret}
                          </button>
                        )}
                      </div>

                      <form onSubmit={confirmMfaEnroll} className="mt-4 flex items-center gap-2">
                        <input
                          type="text"
                          inputMode="numeric"
                          maxLength={6}
                          value={verifyCode}
                          onChange={(e) => setVerifyCode(e.target.value.replace(/\D/g, ""))}
                          placeholder="123456"
                          autoFocus
                          className="flex-1 p-2.5 rounded-lg bg-white/5 border border-white/10 text-center tracking-[0.3em] font-mono text-white placeholder:text-neutral-700 focus:outline-none focus:border-orange-500/50"
                        />
                        <button
                          type="submit"
                          disabled={mfaStatus === "verifying" || verifyCode.length !== 6}
                          className="px-4 py-2.5 rounded-lg bg-gradient-to-r from-orange-500 to-red-600 text-white text-sm font-semibold disabled:opacity-50"
                        >
                          {mfaStatus === "verifying" ? <Loader2 className="w-4 h-4 animate-spin" /> : "Confirm"}
                        </button>
                        <button
                          type="button"
                          onClick={cancelMfaEnroll}
                          className="p-2.5 rounded-lg bg-white/5 border border-white/10 text-neutral-400 hover:text-white"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </form>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              <div>
                <button
                  onClick={toggleSessions}
                  className="w-full flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/10 text-neutral-300 hover:bg-white/10 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <Shield className="w-4 h-4" />
                    <div className="text-left">
                      <p className="text-sm text-white">Active Sessions</p>
                      <p className="text-xs text-neutral-500">Manage logged-in devices</p>
                    </div>
                  </div>
                  <ChevronRight className={`w-4 h-4 text-neutral-500 transition-transform ${showSessions ? "rotate-90" : ""}`} />
                </button>

                <AnimatePresence>
                  {showSessions && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="mt-2 p-3 rounded-xl bg-white/5 border border-white/10 space-y-2">
                        {sessionsStatus === "loading" ? (
                          <div className="flex items-center gap-2 text-sm text-neutral-400 py-2">
                            <Loader2 className="w-4 h-4 animate-spin" /> Loading sessions…
                          </div>
                        ) : sessionsError ? (
                          <div className="flex items-center gap-2 text-sm text-red-400 py-2">
                            <AlertCircle className="w-4 h-4" /> {sessionsError}
                          </div>
                        ) : sessions.length === 0 ? (
                          <p className="text-sm text-neutral-500 py-2">No active sessions found.</p>
                        ) : (
                          sessions.map((s) => (
                            <div key={s.id} className="flex items-center justify-between p-2.5 rounded-lg bg-black/20 border border-white/5">
                              <div>
                                <p className="text-sm text-white flex items-center gap-2">
                                  {describeUserAgent(s.user_agent)}
                                  {s.is_current && (
                                    <span className="text-xs px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">This device</span>
                                  )}
                                </p>
                                <p className="text-xs text-neutral-500">
                                  {s.ip ? `${s.ip} · ` : ""}
                                  Signed in {s.created_at ? new Date(s.created_at).toLocaleString() : "unknown time"}
                                </p>
                              </div>
                            </div>
                          ))
                        )}

                        {sessions.some((s) => !s.is_current) && (
                          <button
                            onClick={revokeOtherSessions}
                            disabled={sessionsStatus === "revoking"}
                            className="w-full mt-1 flex items-center justify-center gap-2 p-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/20 transition-colors text-sm font-medium disabled:opacity-50"
                          >
                            {sessionsStatus === "revoking" ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldOff className="w-4 h-4" />}
                            Sign out all other devices
                          </button>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              <div>
                <button
                  onClick={togglePrivacy}
                  className="w-full flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/10 text-neutral-300 hover:bg-white/10 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <Lock className="w-4 h-4" />
                    <div className="text-left">
                      <p className="text-sm text-white">Privacy Settings</p>
                      <p className="text-xs text-neutral-500">Control your data</p>
                    </div>
                  </div>
                  <ChevronRight className={`w-4 h-4 text-neutral-500 transition-transform ${showPrivacy ? "rotate-90" : ""}`} />
                </button>

                <AnimatePresence>
                  {showPrivacy && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="mt-2 p-3 rounded-xl bg-white/5 border border-white/10 space-y-3">
                        <div>
                          <button
                            onClick={exportData}
                            disabled={exportStatus === "exporting"}
                            className="w-full flex items-center justify-center gap-2 p-2.5 rounded-lg bg-white/5 border border-white/10 text-white hover:bg-white/10 transition-colors text-sm font-medium disabled:opacity-50"
                          >
                            {exportStatus === "exporting" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                            Export my data (JSON)
                          </button>
                          {exportStatus === "error" && (
                            <p className="text-xs text-red-400 mt-1.5 flex items-center gap-1.5"><AlertCircle className="w-3.5 h-3.5" /> {exportError}</p>
                          )}
                        </div>

                        <div className="pt-2 border-t border-white/10">
                          {!showDeleteConfirm ? (
                            <button
                              onClick={() => setShowDeleteConfirm(true)}
                              className="w-full flex items-center justify-center gap-2 p-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/20 transition-colors text-sm font-medium"
                            >
                              Delete my account
                            </button>
                          ) : (
                            <div className="space-y-2">
                              <p className="text-xs text-red-300">
                                This permanently deletes your account, uploads, and issues. This cannot be undone.
                                Type <span className="font-mono font-bold">DELETE</span> to confirm.
                              </p>
                              <input
                                type="text"
                                value={deleteConfirmText}
                                onChange={(e) => setDeleteConfirmText(e.target.value)}
                                placeholder="DELETE"
                                className="w-full p-2.5 rounded-lg bg-black/30 border border-red-500/30 text-white text-sm font-mono focus:outline-none focus:border-red-500/60"
                              />
                              {deleteError && (
                                <p className="text-xs text-red-400 flex items-center gap-1.5"><AlertCircle className="w-3.5 h-3.5" /> {deleteError}</p>
                              )}
                              <div className="flex items-center gap-2">
                                <button
                                  onClick={confirmDeleteAccount}
                                  disabled={deleteConfirmText !== "DELETE" || deleteStatus === "deleting"}
                                  className="flex-1 flex items-center justify-center gap-2 p-2.5 rounded-lg bg-red-600 text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:bg-red-700 transition-colors"
                                >
                                  {deleteStatus === "deleting" ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                                  Permanently delete
                                </button>
                                <button
                                  onClick={() => { setShowDeleteConfirm(false); setDeleteConfirmText(""); setDeleteError(null); }}
                                  className="p-2.5 rounded-lg bg-white/5 border border-white/10 text-neutral-400 hover:text-white"
                                >
                                  <X className="w-4 h-4" />
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
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
