FROM python:3.12-slim

ARG APT_MIRROR=
ARG HERMES_AGENT_VERSION=main
ARG PIP_INDEX_URL=
ARG PIP_TRUSTED_HOST=

# System packages (APT_MIRROR 必须是 HTTP，避免容器内 SSL 问题)
RUN if [ -n "$APT_MIRROR" ]; then \
        sed -i \
          -e "s|http://deb.debian.org/debian-security|${APT_MIRROR}/debian-security|g" \
          -e "s|http://deb.debian.org/debian|${APT_MIRROR}/debian|g" \
          /etc/apt/sources.list.d/debian.sources; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        openssh-client \
        procps \
    && rm -rf /var/lib/apt/lists/*

# Install hermes-agent into a venv inside the image
RUN python3 -m venv /opt/hermes-agent/venv \
    && /opt/hermes-agent/venv/bin/pip install --upgrade pip \
    && cd /tmp \
    && git clone --depth 1 --branch "${HERMES_AGENT_VERSION}" \
       https://github.com/NousResearch/hermes-agent.git \
    && if [ -n "$PIP_INDEX_URL" ]; then \
         /opt/hermes-agent/venv/bin/pip install \
           --index-url "$PIP_INDEX_URL" \
           ${PIP_TRUSTED_HOST:+--trusted-host "$PIP_TRUSTED_HOST"} \
           /tmp/hermes-agent; \
       else \
         /opt/hermes-agent/venv/bin/pip install /tmp/hermes-agent; \
       fi \
    && rm -rf /tmp/hermes-agent

# Install MCP SDK for k3s-cluster MCP server
RUN if [ -n "$PIP_INDEX_URL" ]; then \
      /opt/hermes-agent/venv/bin/pip install \
        --index-url "$PIP_INDEX_URL" \
        ${PIP_TRUSTED_HOST:+--trusted-host "$PIP_TRUSTED_HOST"} \
        "mcp[cli]"; \
    else \
      /opt/hermes-agent/venv/bin/pip install "mcp[cli]"; \
    fi

WORKDIR /workspace
