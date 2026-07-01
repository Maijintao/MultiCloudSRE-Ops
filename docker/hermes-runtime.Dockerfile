FROM python:3.12-slim

ARG APT_MIRROR=

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

WORKDIR /workspace
