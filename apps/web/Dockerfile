# =============================================================================
# Frontend - Next.js
#
# Build context is the REPOSITORY ROOT (this is an npm workspace and the build
# needs packages/shared-types):
#     docker build -f apps/web/Dockerfile -t ocr-web .
#
# KNOWN SIZE TRADE-OFF: the runner stage reuses the full `deps` node_modules,
# devDependencies included, so the image is ~600 MB larger than it needs to be.
# Fixing that properly means `output: "standalone"` in next.config.ts plus a
# prod-only install stage -- a change worth making, but only alongside a real
# container build to verify it, which has not been run.
# =============================================================================

FROM node:20-alpine AS deps
WORKDIR /repo
# Workspace manifests only, so the install layer caches independently of source.
COPY package.json package-lock.json* ./
COPY apps/web/package.json apps/web/
COPY packages/shared-types/package.json packages/shared-types/
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY package.json ./
COPY packages/ ./packages/
COPY apps/web/ ./apps/web/
# BACKEND_URL is read at request time by the rewrite, not baked in here.
RUN npm run build --workspace @ocr-workspace/web

FROM node:20-alpine AS runner
WORKDIR /repo
ENV NODE_ENV=production
COPY --from=deps /repo/node_modules ./node_modules
COPY --from=builder /repo/package.json ./package.json
COPY --from=builder /repo/packages/ ./packages/
COPY --from=builder /repo/apps/web/ ./apps/web/

WORKDIR /repo/apps/web
EXPOSE 3000
CMD ["npm", "run", "start"]
