# Frontend Setup Guide - New Supabase Project

## ✅ Current Status
- Frontend .env already updated with new Supabase credentials
- Database tables created (profiles, roast_results, user_statistics, bulk_jobs, clusters)

## 🔐 Authentication Setup Required

### Step 1: Enable Auth Providers in Supabase Dashboard

Go to: https://supabase.com/dashboard/project/ouxdpbbmvazmtaxeueko/auth/providers

#### Enable Google OAuth:
1. Click on "Google" provider
2. Enable it
3. Add these authorized redirect URLs:
   - `https://ouxdpbbmvazmtaxeueko.supabase.co/auth/v1/callback`
   - `http://localhost:3000/api/auth/callback` (for development)

**Google OAuth Credentials (if needed):**
- Create at: https://console.cloud.google.com/apis/credentials
- Authorized redirect URIs:
  - `https://ouxdpbbmvazmtaxeueko.supabase.co/auth/v1/callback`

#### Enable GitHub OAuth:
1. Click on "GitHub" provider
2. Enable it
3. Add redirect URL: `https://ouxdpbbmvazmtaxeueko.supabase.co/auth/v1/callback`

**GitHub OAuth App (if needed):**
- Create at: https://github.com/settings/developers
- Authorization callback URL: `https://ouxdpbbmvazmtaxeueko.supabase.co/auth/v1/callback`

#### Enable Email Auth:
1. Go to Auth > Providers > Email
2. Enable "Email" provider
3. Enable "Confirm email" (optional, can disable for testing)

### Step 2: Configure Auth Settings

Go to: https://supabase.com/dashboard/project/ouxdpbbmvazmtaxeueko/auth/url-configuration

**Site URL:** `http://localhost:3000` (for development)

**Redirect URLs (add these):**
- `http://localhost:3000/api/auth/callback`
- `http://localhost:3000/dashboard`

### Step 3: Run Frontend

```bash
cd frontend
npm install
npm run dev
```

Open: http://localhost:3000

## 🧪 Test Authentication

1. **Google Login:**
   - Click "Continue with Google"
   - Should redirect to Google OAuth
   - After auth, redirects back to dashboard

2. **Email Login:**
   - Enter email + password
   - Click "Sign in"
   - Should create user and redirect to dashboard

3. **Check Profile:**
   - After login, profile should be auto-created in `profiles` table
   - User stats should be initialized in `user_statistics` table

## 🔍 Troubleshooting

### "Invalid OAuth provider" error:
- Enable the provider in Supabase Dashboard → Authentication → Providers

### "Invalid redirect URL" error:
- Add `http://localhost:3000/api/auth/callback` to Supabase Auth → URL Configuration

### Profile not created:
- Check if trigger `on_auth_user_created` exists:
  ```sql
  SELECT * FROM pg_trigger WHERE tgname = 'on_auth_user_created';
  ```
- If missing, run `setup_all_tables.py` again

### Can't see user in database:
- Check: https://supabase.com/dashboard/project/ouxdpbbmvazmtaxeueko/auth/users
- Users appear in `auth.users` table (managed by Supabase)
- Your custom data is in `public.profiles` table

## 📝 Quick Commands

```bash
# Install dependencies
cd frontend
npm install

# Run development server
npm run dev

# Build for production
npm run build

# Start production server
npm start
```

## ✅ Verification Checklist

- [ ] Google OAuth enabled in Supabase
- [ ] GitHub OAuth enabled in Supabase (optional)
- [ ] Email auth enabled in Supabase
- [ ] Redirect URLs configured
- [ ] Frontend .env has correct Supabase URL and keys
- [ ] Database tables created (profiles, roast_results, user_statistics)
- [ ] RLS policies enabled
- [ ] Triggers configured (on_auth_user_created)
- [ ] Frontend runs without errors (`npm run dev`)
- [ ] Can login with Google/email
- [ ] Profile created automatically after login
- [ ] Can access dashboard after login

## 🚀 Ready to Go!

Once all auth providers are enabled in Supabase dashboard, your frontend will work perfectly!
