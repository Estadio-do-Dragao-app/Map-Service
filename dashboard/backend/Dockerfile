FROM python:3.11-slim

WORKDIR /app

# Copiar o ficheiro de dependências e instalar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo o código da aplicação
COPY . .

# Variável de ambiente para localizar o Map-Service (ajusta se necessário)
ENV MAP_SERVICE_URL=http://host.docker.internal:8000

# Expor a porta interna (o uvicorn vai usar 8000)
EXPOSE 8000

# Comando para iniciar o servidor
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]