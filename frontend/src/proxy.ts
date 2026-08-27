import { createServerClient } from '@supabase/ssr';
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export async function proxy(req: NextRequest) {
  const res = NextResponse.next();
  
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        get(name: string) {
          return req.cookies.get(name)?.value;
        },
        set(name: string, value: string, options: any) {
          res.cookies.set({ name, value, ...options });
        },
        remove(name: string, options: any) {
          res.cookies.set({ name, value: '', ...options });
        },
      },
    }
  );

  // Refresh session if expired
  const {
    data: { session },
  } = await supabase.auth.getSession();

  // Protected routes -- every page under the (app) route group, plus the
  // internal API proxy. Previously only /dashboard and /settings were
  // listed here; /analytics, /upload, /clusters, /ai-debug relied solely
  // on a client-side redirect in each page's own useEffect, which only
  // fires after the page has already started rendering (and wouldn't have
  // enforced the aal2 two-factor gate below at all).
  const protectedPaths = ['/dashboard', '/settings', '/analytics', '/upload', '/clusters', '/ai-debug', '/api/roast'];
  const isProtectedPath = protectedPaths.some((path) =>
    req.nextUrl.pathname.startsWith(path)
  );

  // Redirect to login if not authenticated and trying to access protected route
  if (isProtectedPath && !session) {
    const redirectUrl = new URL('/login', req.url);
    redirectUrl.searchParams.set('redirect', req.nextUrl.pathname);
    return NextResponse.redirect(redirectUrl);
  }

  // Two-factor gate -- lives here (not in the login page) so it applies no
  // matter how the session was created (password, Google OAuth, GitHub
  // OAuth, or a still-valid cookie from a previous visit). A session can be
  // real and authenticated (aal1) but the account still requires a second
  // factor (aal2) before it should be allowed into anything protected --
  // without this check here, enrolling a TOTP factor in Settings would be
  // pure decoration: nothing would ever actually ask for the code.
  if (isProtectedPath && session) {
    const { data: aal } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
    if (aal && aal.nextLevel === 'aal2' && aal.currentLevel !== aal.nextLevel) {
      return NextResponse.redirect(new URL('/verify-2fa', req.url));
    }
  }

  // Redirect to dashboard if authenticated and trying to access auth pages
  if (session && (req.nextUrl.pathname === '/login' || req.nextUrl.pathname === '/signup')) {
    return NextResponse.redirect(new URL('/dashboard', req.url));
  }

  return res;
}

export const config = {
  matcher: [
    '/dashboard/:path*',
    '/settings/:path*',
    '/analytics/:path*',
    '/upload/:path*',
    '/clusters/:path*',
    '/ai-debug/:path*',
    '/login',
    '/signup',
    '/api/roast/:path*',
  ],
};
