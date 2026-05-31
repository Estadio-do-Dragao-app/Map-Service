FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer cache optimization)
COPY requirements.lock.txt .
RUN pip install --no-cache-dir --only-binary :all: -r requirements.lock.txt \
    && useradd -m -u 1000 appuser

# Copy only necessary application files (avoid sensitive data leakage)
COPY main.py database.py models.py ./

RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Variável de ambiente para localizar o Map-Service (ajusta se necessário)
ENV MAP_SERVICE_URL=http://host.docker.internal:8000

# Expor a porta interna (o uvicorn vai usar 8000)
EXPOSE 8000

# Comando para iniciar o servidor
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
