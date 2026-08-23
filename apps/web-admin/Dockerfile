FROM node:20-alpine AS base
RUN apk add --no-cache libc6-compat

ARG NEXT_PUBLIC_GATEWAY_URL=http://localhost:8000/api/v1

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
COPY apps/web-admin/package.json apps/web-admin/package-lock.json* ./apps/web-admin/
WORKDIR /app/apps/web-admin
RUN npm ci

# Build
FROM base AS builder
WORKDIR /app
ARG NEXT_PUBLIC_GATEWAY_URL
ENV NEXT_PUBLIC_GATEWAY_URL=$NEXT_PUBLIC_GATEWAY_URL
COPY --from=deps /app/packages/shared-ts ./packages/shared-ts
COPY --from=deps /app/apps/web-admin/node_modules ./apps/web-admin/node_modules
COPY apps/web-admin ./apps/web-admin
WORKDIR /app/apps/web-admin

# Next.js collects completely anonymous telemetry data about general usage.
# Learn more here: https://nextjs.org/telemetry
# Uncomment the following line in case you want to disable telemetry during the build.
# ENV NEXT_TELEMETRY_DISABLED 1

RUN npm run build

# Production image
FROM base AS runner

ENV NODE_ENV=production
ARG NEXT_PUBLIC_GATEWAY_URL=http://localhost:8000/api/v1
ENV NEXT_PUBLIC_GATEWAY_URL=$NEXT_PUBLIC_GATEWAY_URL
# Uncomment the following line in case you want to disable telemetry during runtime.
# ENV NEXT_TELEMETRY_DISABLED 1

# Create user first so we can use --chown on COPY (avoids slow chown -R over node_modules)
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

# Only copy the standalone output
COPY --from=builder --chown=nextjs:nodejs /app/apps/web-admin/.next/standalone /app/apps/web-admin/.next/standalone
COPY --from=builder --chown=nextjs:nodejs /app/apps/web-admin/.next/static /app/apps/web-admin/.next/standalone/.next/static

WORKDIR /app/apps/web-admin/.next/standalone

USER nextjs

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/', r => process.exit(r.statusCode < 500 ? 0 : 1)).on('error', () => process.exit(1))"

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
