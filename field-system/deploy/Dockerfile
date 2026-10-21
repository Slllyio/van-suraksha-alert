# Python environment only. The code and data live in the mounted /srv/fire tree (same layout as the project folder),
# so a code update is `git pull` + `docker compose restart`, never an image rebuild.
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 tini curl ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
ENV PYTHONUNBUFFERED=1 TZ=UTC
WORKDIR /mnt/project-files/field-system
ENTRYPOINT ["tini", "--"]
