# Map-Service

Backend API para gestão de mapas indoor do Estádio do Dragão.

### 1. Start PostgreSQL (Docker)
```bash
docker-compose up -d
```

### 2. Setup Python Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Load Sample Data
```bash
python3 load_data_db.py
```
### Reset DB Data
```bash
curl -X POST http://localhost:8000/api/reset
```

### 4. Run API
```bash
uvicorn ApiHandler:app --reload
```

API em: `http://localhost:8000`  
Docs: `http://localhost:8000/docs`

## 🐳 Docker Commands

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

## 📊 Database

- **Type:** PostgreSQL 15
- **Port:** 5432
- **Database:** estadio_do_dragao
- **User/Pass:** postgres/postgres

## 📡 API Endpoints

- `GET /api/map` - Complete map data
- `GET /api/nodes` - All nodes
- `POST /api/nodes` - Create node
- `GET /api/edges` - All edges
- `POST /api/edges` - Create edge
- `GET /api/closures` - All closures
- `POST /api/closures` - Create closure