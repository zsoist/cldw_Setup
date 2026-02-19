# OpenClaw Gateway Docker image for Hetzner CPX22
# Optimized for 3 vCPU / 4GB RAM environment
FROM node:20-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r openclaw && useradd -r -g openclaw -m -d /home/node openclaw

# Set working directory
WORKDIR /home/node

# Clone and install OpenClaw (pinned to stable)
RUN git clone https://github.com/openclaw/openclaw.git /home/node/openclaw \
    && cd /home/node/openclaw \
    && npm ci --production

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
CMD ["node", "src/gateway.js"]
