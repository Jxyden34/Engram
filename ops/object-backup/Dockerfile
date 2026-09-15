FROM quay.io/minio/mc@sha256:a7fe349ef4bd8521fb8497f55c6042871b2ae640607cf99d9bede5e9bdf11727 AS mc
FROM alpine:3.22
RUN apk add --no-cache openssl tar
COPY --from=mc /usr/bin/mc /usr/bin/mc
COPY backup.sh /usr/local/bin/backup.sh
RUN chmod +x /usr/local/bin/backup.sh
CMD ["/usr/local/bin/backup.sh"]
