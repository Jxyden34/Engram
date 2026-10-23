FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv

WORKDIR /srv

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS source
ARG ENGRAM_EDITION=community
COPY app /source/app
COPY scripts /source/scripts
RUN case "$ENGRAM_EDITION" in community|commercial) ;; *) exit 1 ;; esac \
    && printf '%s' "$ENGRAM_EDITION" > /source/app/EDITION \
    && rm -f /source/scripts/commercial_license.py \
    && if [ "$ENGRAM_EDITION" = community ]; then \
         rm -rf /source/app/commercial /source/scripts/commercial_license.py; \
       fi

FROM base AS runtime
COPY --from=source /source/app ./app
COPY --from=source /source/scripts ./scripts

RUN useradd --create-home --uid 10001 engram
USER engram

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
