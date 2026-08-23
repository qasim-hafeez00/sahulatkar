FROM node:26-alpine AS base
RUN apk add --no-cache libc6-compat

ARG NEXT_PUBLIC_API_URL=http://localhost:8000

# Install dependencies (resolves the local sk-shared-ts workspace dependency).
# sk-shared-ts is consumed via `file:../../packages/shared-ts`, not an npm
# workspace, so its own dependencies (e.g. jose) must be installed directly
# inside packages/shared-ts too — Node resolves imports from that package's
# own node_modules, not from the app's.
FROM base AS deps
WORKDIR /app
COPY packages/shared-ts ./packages/shared-ts
WORKDIR /app/packages/shared-ts
RUN npm ci
WORKDIR /app
COPY apps/web-customer/package.json apps/web-customer/package-lock.json* ./apps/web-customer/
WORKDIR /app/apps/web-customer
RUN npm ci

# Build
FROM base AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
COPY --from=deps /app/packages/shared-ts ./packages/shared-ts
COPY --from=deps /app/apps/web-customer/node_modules ./apps/web-customer/node_modules
COPY apps/web-customer ./apps/web-customer
WORKDIR /app/apps/web-customer

# Next.js collects completely anonymous telemetry data about general usage.
# Learn more here: https://nextjs.org/telemetry
# Uncomment the following line in case you want to disable telemetry during the build.
# ENV NEXT_TELEMETRY_DISABLED 1

RUN npm run build

# Production image
FROM base AS runner

ENV NODE_ENV=production
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
# Uncomment the following line in case you want to disable telemetry during runtime.
# ENV NEXT_TELEMETRY_DISABLED 1

# Create user first so we can use --chown on COPY (avoids slow chown -R over node_modules)
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

# Only copy the standalone output — not the full build tree with node_modules
COPY --from=builder --chown=nextjs:nodejs /app/packages/shared-ts /app/packages/shared-ts
COPY --from=builder --chown=nextjs:nodejs /app/apps/web-customer/.next/standalone /app/apps/web-customer/.next/standalone
COPY --from=builder --chown=nextjs:nodejs /app/apps/web-customer/.next/static /app/apps/web-customer/.next/standalone/apps/web-customer/.next/static
COPY --from=builder --chown=nextjs:nodejs /app/apps/web-customer/public /app/apps/web-customer/.next/standalone/apps/web-customer/public

WORKDIR /app/apps/web-customer/.next/standalone/apps/web-customer

USER nextjs

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/', r => process.exit(r.statusCode < 500 ? 0 : 1)).on('error', () => process.exit(1))"

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
