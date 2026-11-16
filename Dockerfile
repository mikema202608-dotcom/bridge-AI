FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 SCHOOL_BIND=0.0.0.0 SCHOOL_PORT=8766 SCHOOL_DATA=/data
WORKDIR /app
RUN groupadd --gid 10001 school && useradd --uid 10001 --gid 10001 --no-create-home school \
    && install -d -m 0700 -o school -g school /data
COPY server.py client.js style.css ./
USER school
EXPOSE 8766
CMD ["python", "server.py"]
