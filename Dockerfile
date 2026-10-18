FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app \
    PORT=8080

WORKDIR /app

# Install dependencies first so this layer is cached between code-only changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user.
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8080

# On start: bring the schema up to date, add starter dishes if the table is empty, then serve.
CMD ["sh", "-c", "flask db upgrade && flask seed && exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 0 app:app"]
