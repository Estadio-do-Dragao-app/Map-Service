#!/bin/bash
# NÃO usar set -e aqui porque queremos capturar exit codes específicos

echo "Checking database..."

# Wait for database to be ready
python -c "
from database import SessionLocal, init_db
from models import Node
import time

max_retries = 30
for i in range(max_retries):
    try:
        init_db()
        db = SessionLocal()
        count = db.query(Node).count()
        db.close()
        print(f'Database ready. Found {count} nodes.')
        if count == 0:
            print('Database is empty. Loading data...')
            exit(1)  # Signal to load data
        else:
            print('Database already has data.')
            exit(0)  # Signal no need to load
    except Exception as e:
        print(f'Waiting for database... ({i+1}/{max_retries})')
        time.sleep(1)
print('Database connection failed!')
exit(2)
"

# Check the exit code
DB_STATUS=$?

if [ $DB_STATUS -eq 1 ]; then
    echo "Loading stadium data..."
    python load_data_db.py
    
    # Verificar se carregou corretamente
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to load data!"
        exit 1
    fi
    echo "Data loaded successfully!"
elif [ $DB_STATUS -eq 2 ]; then
    echo "ERROR: Database connection failed!"
    exit 1
fi

echo "Starting API server..."
exec uvicorn ApiHandler:app --host 0.0.0.0 --port 8000

