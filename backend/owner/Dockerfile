FROM python:3.14-slim
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 engram && mkdir /data && chown engram /data
COPY app/config.py app/edition.py app/licensing.py ./app/
COPY scripts/commercial_license.py ./scripts/
COPY owner ./owner
USER engram
EXPOSE 8091
CMD ["uvicorn", "owner.service:app", "--host", "0.0.0.0", "--port", "8091"]
