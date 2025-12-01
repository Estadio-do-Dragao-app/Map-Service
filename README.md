# Map-Service

Backend API para gestão de mapas indoor do Estádio do Dragão.

### 1. Start PostgreSQL (Docker)
```bash
docker-compose up -d
```

### 2. Create .env file
```bash
cp .env.example .env
# Edit .env if needed (default values work with Docker)
```

### 3. Setup Python Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Load Sample Data
```bash
python3 load_data_db.py
```

### 5. Run API
```bash
uvicorn ApiHandler:app --reload
```

API em: `http://localhost:8000`  
Docs: `http://localhost:8000/docs`

## Reset Database
```bash
curl -X POST http://localhost:8000/api/reset
```

## Docker Commands

```bash
# Start database
docker-compose up -d

# Stop database
docker-compose down

# Stop and remove data
docker-compose down -v

# View logs
docker-compose logs -f postgres
```
