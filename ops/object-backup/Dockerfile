FROM minio/mc:latest AS mc
FROM alpine:3.22
RUN apk add --no-cache openssl tar
COPY --from=mc /usr/bin/mc /usr/bin/mc
COPY backup.sh /usr/local/bin/backup.sh
RUN chmod +x /usr/local/bin/backup.sh
CMD ["/usr/local/bin/backup.sh"]
