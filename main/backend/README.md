# Pālo Queue Management — Backend

FastAPI + SQLAlchemy backend for the Pālo queue management system.

## Tech Stack
- **FastAPI** — API framework
- **SQLAlchemy 2.x** — ORM (SQLite default, PostgreSQL supported)
- **scikit-learn + numpy** — ML wait-time prediction engine
- **Uvicorn** — ASGI server

## Setup

### 1. Create a virtual environment
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure environment (optional)
```bash
copy .env.example .env
# Edit .env if you want to use PostgreSQL
```

### 4. Run the server
```bash
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/organizations` | Create organization |
| POST | `/organizations/{id}/queues` | Create queue |
| POST | `/queues/{id}/tokens` | Join queue (get token) |
| GET | `/queues/{id}/tokens` | List all tokens |
| PATCH | `/tokens/{id}` | Update token state |
| GET | `/queues/{id}/stats` | Queue statistics |
| GET | `/queues/{id}/operator-view` | Operator dashboard data |
| POST | `/queues/{id}/counters` | Create counter |
| POST | `/ml/train` | Train ML model |
| GET | `/ml/model-info` | ML model info |

## Project Structure

```
backend/
├── main.py          # FastAPI app + all route handlers
├── models.py        # SQLAlchemy ORM models
├── schemas.py       # Pydantic request/response schemas
├── database.py      # DB engine + session management
├── ml_engine.py     # ML wait-time prediction engine
├── requirements.txt # pip dependencies
├── pyproject.toml   # Project metadata
└── .env.example     # Environment variable template
```
