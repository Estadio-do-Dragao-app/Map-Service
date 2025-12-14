FROM python:3.11-slim

WORKDIR /app

# Install bash and dos2unix for entrypoint script
RUN apt-get update && apt-get install -y --no-install-recommends bash dos2unix && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only necessary files instead of entire directory
COPY *.py ./
COPY stadiums/ ./stadiums/
COPY entrypoint.sh ./

# Fix line endings and make entrypoint executable, then set ownership
RUN dos2unix entrypoint.sh && chmod +x entrypoint.sh && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

ENTRYPOINT ["./entrypoint.sh"]
