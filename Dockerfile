FROM python:3.12-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY collector.py run-on-coolify.sh git-askpass.sh ./
RUN chmod 0755 /app/run-on-coolify.sh /app/git-askpass.sh

ENV BACKFILL_DAYS=7
ENV BVB_EXCHSEGMENT=BSE

# Coolify Scheduled Tasks execute inside this running application container.
CMD ["sleep", "infinity"]
