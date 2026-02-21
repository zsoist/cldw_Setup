# OpenClaw Gateway Docker image for Hetzner CPX22
# Optimized for 3 vCPU / 4GB RAM environment
FROM node:22-bookworm

ARG OPENCLAW_REPO=https://github.com/openclaw/openclaw.git
ARG OPENCLAW_REF=58f7b7638a997ebb7da3a4877e6c64c40bc20e7e

# Build-time source controls
ARG OPENCLAW_REPO=https://github.com/openclaw/openclaw.git
ARG OPENCLAW_REF=58f7b7638a997ebb7da3a4877e6c64c40bc20e7e

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Enable corepack for pnpm (OpenClaw uses pnpm workspace lockfile)
RUN corepack enable

# Create non-root user
RUN groupadd -r openclaw && useradd -r -g openclaw -m -d /home/node openclaw

# Set working directory
WORKDIR /home/node

# Clone and build OpenClaw (pinned for reproducible builds)
RUN git clone "$OPENCLAW_REPO" /home/node/openclaw \
    && cd /home/node/openclaw \
    && git checkout "$OPENCLAW_REF" \
    && pnpm install --frozen-lockfile \
    && pnpm build \
    && OPENCLAW_PREFER_PNPM=1 pnpm ui:build \
    && rm -rf .git

# Copy configuration
COPY openclaw-config.json /home/node/.openclaw/openclaw.json

# Set ownership
RUN chown -R openclaw:openclaw /home/node

# Switch to non-root user
USER openclaw

# Expose gateway port (loopback only in docker-compose)
EXPOSE 18789

# Health check
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
    CMD curl -sf http://127.0.0.1:18789/ || exit 1

# Start the gateway
WORKDIR /home/node/openclaw
CMD ["node", "openclaw.mjs", "gateway", "--allow-unconfigured"]
