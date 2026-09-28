FROM postgres:18-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       openssl \
       tar \
       gzip \
       coreutils \
       findutils \
       rclone \
       jq \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY monitor.sh /usr/local/bin/monitor.sh
RUN chmod +x /usr/local/bin/monitor.sh

CMD ["/usr/local/bin/monitor.sh"]
