# Production image for the Next.js frontend.
#
# Multi-stage so the shipped image carries only the standalone server output
# (next.config.ts sets output: "standalone"), not the full node_modules or the
# build toolchain.
#
# NEXT_PUBLIC_* values are inlined into the client bundle at BUILD time. Next
# reads them from the .env in the build context automatically, so the browser
# ships with the right Supabase URL/anon key and API URL. Runtime-only secrets
# (SUPABASE_SERVICE_ROLE_KEY, BACKEND_URL, ...) are NOT baked here — they come
# from the container environment at run time (see docker-compose.yml).

# ---------- deps ----------
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---------- builder ----------
FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ---------- runner ----------
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

# Standalone output + static assets + public dir are all that's needed to run.
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

CMD ["node", "server.js"]
