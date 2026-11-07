FROM python:3.12-slim
WORKDIR /app
RUN useradd --create-home appuser && mkdir -p /app/link-jobs && chown appuser:appuser /app/link-jobs
COPY --chown=appuser:appuser . .
USER appuser
ENV PORT=8080 PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "server.py"]
