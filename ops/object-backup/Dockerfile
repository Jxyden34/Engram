FROM docker.io/pgsty/mc@sha256:cfc83108c3abb371f8fb84d99c1fdc88f8c237e022409b0081fb7c0a3be634dd AS mc
FROM alpine:3.22
RUN apk add --no-cache openssl tar
COPY --from=mc /usr/bin/mc /usr/bin/mc
COPY backup.sh /usr/local/bin/backup.sh
RUN chmod +x /usr/local/bin/backup.sh
CMD ["/usr/local/bin/backup.sh"]
