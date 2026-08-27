"use client";

/**
 * Two-Factor Challenge - shown after password/OAuth sign-in when the
 * account has a verified TOTP factor and the current session is only
 * aal1. proxy.ts redirects here for any protected route while stuck at
 * aal1 with aal2 required, so this page is the one place that actually
 * enforces 2FA rather than just decorating Settings with a toggle.
 */

import { motion } from "framer-motion";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ShieldCheck, Loader2, AlertCircle } from "lucide-react";
import { supabase } from "@/lib/supabase/client";

export default function Verify2FAPage() {
  const router = useRouter();
  const [factorId, setFactorId] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    (async () => {
      const { data: aal } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
      // Nothing to challenge -- either no MFA on this account, or the
      // session is already aal2 (e.g. a stale tab reload after verifying).
      // Don't strand the user on this page in either case.
      if (!aal || aal.nextLevel !== "aal2" || aal.currentLevel === aal.nextLevel) {
        router.replace("/dashboard");
        return;
      }

      const { data: factors, error: listError } = await supabase.auth.mfa.listFactors();
      const verifiedTotp = factors?.totp?.find((f) => f.status === "verified");
      if (listError || !verifiedTotp) {
        // aal says a challenge is needed but there's no factor to challenge --
        // shouldn't happen, but fail open to the dashboard rather than
        // stranding the user on a dead-end page with no way forward.
        router.replace("/dashboard");
        return;
      }

      setFactorId(verifiedTotp.id);
      setChecking(false);
    })();
  }, [router]);

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!factorId) return;
    setSubmitting(true);
    setError("");

    const { error: verifyError } = await supabase.auth.mfa.challengeAndVerify({
      factorId,
      code: code.trim(),
    });

    if (verifyError) {
      setError(verifyError.message || "Invalid code — try again.");
      setSubmitting(false);
      return;
    }

    // Full navigation (not router.push) so the middleware re-evaluates the
    // session server-side with the now-elevated aal2 cookie.
    window.location.href = "/dashboard";
  };

  const handleSignOut = async () => {
    await supabase.auth.signOut();
    router.replace("/login");
  };

  if (checking) {
    return (
      <div className="flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-neutral-500" />
      </div>
    );
  }

  return (
    <div className="w-full max-w-md">
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center mb-8"
      >
        <Link href="/" className="inline-flex items-center gap-2">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-orange-500 to-red-600 flex items-center justify-center shadow-lg shadow-orange-500/25">
            <span className="text-2xl">🔥</span>
          </div>
          <span className="font-black text-3xl bg-gradient-to-r from-orange-500 to-red-600 bg-clip-text text-transparent">
            ROAST
          </span>
        </Link>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="relative rounded-3xl bg-white/5 backdrop-blur-xl border border-white/10 p-8 shadow-2xl"
      >
        <div className="absolute -top-20 left-1/2 -translate-x-1/2 w-64 h-64 bg-orange-500/20 rounded-full blur-3xl pointer-events-none" />

        <div className="relative text-center mb-8">
          <div className="w-12 h-12 mx-auto mb-4 rounded-2xl bg-orange-500/10 border border-orange-500/20 flex items-center justify-center">
            <ShieldCheck className="w-6 h-6 text-orange-400" />
          </div>
          <h1 className="text-2xl font-bold text-white mb-2">Two-factor check</h1>
          <p className="text-neutral-400 text-sm">Enter the 6-digit code from your authenticator app</p>
        </div>

        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="relative mb-6 p-4 rounded-xl bg-red-500/10 border border-red-500/20 flex items-start gap-3"
          >
            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-red-300">{error}</p>
          </motion.div>
        )}

        <form onSubmit={handleVerify} className="relative space-y-4">
          <input
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            placeholder="000000"
            autoFocus
            className="w-full text-center tracking-[0.5em] text-2xl font-mono py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder:text-neutral-700 focus:outline-none focus:border-orange-500/50 focus:ring-1 focus:ring-orange-500/50 transition-all"
          />

          <button
            type="submit"
            disabled={submitting || code.length !== 6}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-gradient-to-r from-orange-500 to-red-600 text-white font-semibold hover:shadow-lg hover:shadow-orange-500/25 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {submitting ? <Loader2 className="w-5 h-5 animate-spin" /> : "Verify"}
          </button>
        </form>

        <button
          onClick={handleSignOut}
          className="relative w-full text-center text-sm text-neutral-500 hover:text-neutral-300 transition-colors mt-6"
        >
          Not you? Sign out
        </button>
      </motion.div>
    </div>
  );
}
