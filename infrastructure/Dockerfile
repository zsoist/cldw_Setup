# OpenClaw Gateway Docker image for Hetzner CPX22
# Optimized for 3 vCPU / 4GB RAM environment

FROM node:22-bookworm AS builder

ARG OPENCLAW_REPO=https://github.com/openclaw/openclaw.git
ARG OPENCLAW_REF=v2026.3.7

RUN apt-get update && apt-get install -y \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN corepack enable

WORKDIR /tmp

# Clone and build OpenClaw (pinned for reproducible builds)
RUN git clone "$OPENCLAW_REPO" /tmp/openclaw \
    && cd /tmp/openclaw \
    && git checkout "$OPENCLAW_REF" \
    && pnpm install --frozen-lockfile \
    && pnpm build \
    && OPENCLAW_PREFER_PNPM=1 pnpm ui:build \
    && rm -rf .git


FROM node:22-bookworm-slim

RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r openclaw && useradd -r -g openclaw -m -d /home/node openclaw

WORKDIR /home/node

# Copy runtime artifacts only (no git history or build tooling metadata)
COPY --from=builder /tmp/openclaw /home/node/openclaw
# Config is provided via volume mount at runtime (/root/.openclaw:/home/node/.openclaw)
RUN mkdir -p /home/node/.openclaw

RUN chown -R openclaw:openclaw /home/node

USER openclaw

EXPOSE 18789

HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
    CMD curl -sf http://127.0.0.1:18789/ || exit 1

WORKDIR /home/node/openclaw
CMD ["node", "openclaw.mjs", "gateway", "--allow-unconfigured"]
