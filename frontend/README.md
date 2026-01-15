# 🔥 ROAST - Turn Brutal Reviews into Engineering Tickets

[![Next.js](https://img.shields.io/badge/Next.js-16.1.1-black?style=flat-square&logo=next.js)](https://nextjs.org)
[![Supabase](https://img.shields.io/badge/Supabase-Auth%20%2B%20DB-3ECF8E?style=flat-square&logo=supabase)](https://supabase.com)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0-blue?style=flat-square&logo=typescript)](https://www.typescriptlang.org)
[![Framer Motion](https://img.shields.io/badge/Framer%20Motion-Animations-ff69b4?style=flat-square)](https://www.framer.com/motion/)

> **AI-powered SaaS** that transforms user complaints into actionable engineering tickets with a cyber-industrial design system.

---

## ✨ Features

### 🔐 **Authentication**
- **OAuth Integration**: Google & GitHub sign-in via Supabase Auth
- **Session Management**: Server-side cookies with @supabase/ssr
- **Protected Routes**: Middleware-based route protection

### 🎨 **Design System**
- **Cyber-Industrial Aesthetic**: Void black, magma red, frosted glass
- **Theme Toggle**: Light/Dark mode with persistent state
- **Premium Fonts**: Space Grotesk, Inter, Azeret Mono
- **Smooth Animations**: Framer Motion for micro-interactions

### 📊 **Dashboard**
- **User Statistics**: Review count, tickets created, success rate
- **Roast History**: Timeline of analyzed reviews
- **Real-time Updates**: Live data from Supabase

### 🗂️ **Navigation**
- **Glass Dock Sidebar**: Floating navigation with active indicators
- **Holographic Header**: User profile dropdown with avatar
- **Multi-page Setup**: Dashboard, Upload, Clusters, Analytics, Settings

---

## 🚀 Getting Started

### Prerequisites
```bash
Node.js 18+ 
npm/yarn/pnpm/bun
Supabase account
```

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd frontend
```

2. **Install dependencies**
```bash
npm install
```

3. **Configure environment variables**
Create a `.env.local` file:
```env
NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

4. **Set up Supabase database**
Run the schema in Supabase SQL Editor:
```bash
# See database/schema.sql for full schema
```

5. **Configure OAuth providers**
In Supabase Dashboard → Authentication → Providers:
- Enable Google OAuth
- Enable GitHub OAuth
- Add redirect URL: `https://[your-project].supabase.co/auth/v1/callback`

6. **Run the development server**
```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

---

## 📁 Project Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── (app)/              # Protected app routes
│   │   │   ├── dashboard/      # Main dashboard
│   │   │   ├── upload/         # File upload
│   │   │   ├── clusters/       # Review clustering
│   │   │   ├── analytics/      # Analytics dashboard
│   │   │   └── settings/       # User settings
│   │   ├── (auth)/             # Auth routes
│   │   │   └── login/          # Login page
│   │   ├── (marketing)/        # Public routes
│   │   │   └── page.tsx        # Landing page
│   │   ├── api/
│   │   │   └── auth/
│   │   │       ├── callback/   # OAuth callback
│   │   │       └── signout/    # Sign out endpoint
│   │   ├── layout.tsx          # Root layout
│   │   └── globals.css         # Global styles
│   ├── components/
│   │   ├── layout/
│   │   │   ├── HoloHeader.tsx  # Top navigation
│   │   │   └── GlassDock.tsx   # Side navigation
│   │   ├── providers/
│   │   │   └── ThemeProvider.tsx # Theme manager
│   │   └── ui/                 # UI components
│   ├── lib/
│   │   └── supabase/
│   │       ├── client.ts       # Browser client
│   │       ├── server.ts       # Server client
│   │       └── admin.ts        # Admin client
│   └── middleware.ts           # Route protection
├── database/
│   ├── schema.sql              # Database schema
│   └── setup.ts                # Setup script
├── public/
│   └── logo.png                # Brand logo
└── package.json
```

---

## 🗄️ Database Schema

### Tables
- **profiles**: User profile data
- **roast_results**: Analyzed review results
- **user_statistics**: User activity stats

### Security
- Row Level Security (RLS) enabled
- Automatic triggers for profile creation
- User-based data isolation

---

## 🎨 Tech Stack

| Category | Technology |
|----------|-----------|
| **Framework** | Next.js 16.1.1 (App Router) |
| **Language** | TypeScript 5.0 |
| **Styling** | Tailwind CSS v4 |
| **Database** | Supabase (PostgreSQL) |
| **Auth** | Supabase Auth (OAuth) |
| **Animations** | Framer Motion |
| **Fonts** | Space Grotesk, Inter, Azeret Mono |
| **State** | React Hooks |
| **Deployment** | Vercel (recommended) |

---

## 🎯 Available Scripts

```bash
npm run dev          # Start development server
npm run build        # Build for production
npm run start        # Start production server
npm run lint         # Run ESLint
npm run type-check   # Run TypeScript checks
```

---

## 🔑 Environment Variables

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_SUPABASE_URL` | Your Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anonymous key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (server-only) |

---

## 🌈 Theme System

### Dark Mode (Default)
- Background: Void Black (#030303)
- Text: Off-white (#ededed)
- Accents: Magma Red (#FF2E00)

### Light Mode
- Background: Light Gray (#f5f5f7)
- Text: Dark Gray (#1a1a1a)
- Accents: Magma Red (unchanged)

Toggle theme in Settings page.

---

## 🔐 Authentication Flow

1. User clicks "Sign in with Google/GitHub"
2. Redirects to Supabase OAuth
3. User authorizes app
4. Callback to `/api/auth/callback`
5. Session created, redirect to `/dashboard`

---

## 📦 Key Dependencies

```json
{
  "@supabase/supabase-js": "^2.39.0",
  "@supabase/ssr": "^0.5.0",
  "framer-motion": "^11.0.0",
  "next": "16.1.1",
  "react": "^19.0.0",
  "tailwindcss": "^4.0.0",
  "lucide-react": "^0.468.0"
}
```

---

## 🚧 Roadmap

- [ ] Implement AI review analysis API
- [ ] Build file upload functionality
- [ ] Create clustering algorithm
- [ ] Add analytics charts
- [ ] Implement ticket export
- [ ] Add real-time notifications
- [ ] Build team collaboration features

---

## 📝 License

MIT License - see LICENSE file for details

---

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines first.

---

## 📧 Support

For issues or questions, open an issue on GitHub or contact the team.

---

**Built with 🔥 by Illu Minaati**
