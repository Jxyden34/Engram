FROM docker.io/pgsty/mc@sha256:cfc83108c3abb371f8fb84d99c1fdc88f8c237e022409b0081fb7c0a3be634dd AS mc
FROM alpine:3.22
RUN apk add --no-cache ca-certificates
COPY --from=mc /usr/bin/mc /usr/bin/mc
