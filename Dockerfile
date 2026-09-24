FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY demo ./demo
RUN pip install --no-cache-dir .

ENV ROUTER_DATA_DIR=/app/demo \
    ROUTER_FEEDBACK_FILE=/data/feedback.jsonl
VOLUME /data

CMD ["escalation-router-slack"]
