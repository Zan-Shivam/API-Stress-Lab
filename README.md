# API Stress Lab

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-yellow)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED)](https://docs.docker.com/compose/)

A simple, self-hosted web application for stress-testing APIs. Run load tests against any HTTP endpoint, monitor live progress via WebSocket, and review historical results with detailed metrics (e.g., latency percentiles, RPS, error rates). Built with FastAPI, SQLAlchemy, RQ (for background jobs), and async HTTP clients.



<video width='200' height='200' src = "https://github.com/user-attachments/assets/b8ef354d-43fd-4aa0-983c-3343095d05b4"> /video>


## Features

- **Web UI**: Intuitive interface to configure and launch tests (served from `/`).
- **Live Updates**: Real-time progress and metrics via WebSocket.
- **Background Processing**: Tests run asynchronously using RQ workers to avoid blocking.
- **Metrics Dashboard**: Track latency (avg, p50/p90/p95/p99), throughput (RPS), success/failure rates, and status code distributions.
- **History & Storage**: Persist test results in a database (SQLite for dev, PostgreSQL for prod).
- **CLI Mode**: Standalone load testing script for scripting/automation.
- **Containerized**: Easy deployment with Docker Compose (includes Postgres, Redis, web server, and worker).

## Quick Start

### Prerequisites
- Python 3.11+
- Docker (for containerized setup)
- Redis (for job queuing)

### Local Development (SQLite + Redis)
1. Clone the repo:
   ```
   git clone https://github.com/Zan-Shivam/API-Stress-Lab.git
   cd API-Stress-Lab
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Start Redis (e.g., via Docker):
   ```
   docker run -d -p 6379:6379 --name redis redis:7
   ```

4. Run the FastAPI server:
   ```
   uvicorn api_main:app --host 0.0.0.0 --port 8000 --reload
   ```

5. Open http://localhost:8000 in your browser to access the UI.

### Docker Compose (Recommended for Production)
1. Ensure Docker and Docker Compose are installed.

2. Start all services (Postgres, Redis, web, worker):
   ```
   docker-compose up -d
   ```

3. Access the UI at http://localhost:8000.

4. View logs:
   ```
   docker-compose logs -f web  # or worker
   ```

5. Stop services:
   ```
   docker-compose down
   ```

**Environment Variables**:
- `DATABASE_URL`: Database connection (default: `sqlite:///./stresslab.db`).
- `REDIS_URL`: Redis connection (default: `redis://localhost:6379/0`).

## Usage

### Web UI
1. Navigate to http://localhost:8000.
2. Enter the target API URL (e.g., `https://httpbin.org/delay/1`).
3. Configure:
   - HTTP Method (default: GET).
   - Total Requests (1–1000, default: 50).
   - Concurrency (1–200, default: 10).
   - Optional Label for the test.
4. Click "Run Test" – progress updates live via WebSocket.
5. View results: Summary metrics, timeseries data, and full history.

### API Endpoints
The backend exposes a RESTful API (docs at http://localhost:8000/docs).

- **POST /run-test**: Queue a new load test.
  - Body: `{ "url": "https://example.com/api", "method": "POST", "total_requests": 100, "concurrency": 20, "label": "My Test" }`
  - Response: TestRunDetail (includes ID for WebSocket subscription).

- **GET /tests**: List all test runs (paginated by creation date).

- **GET /tests/{test_id}**: Fetch detailed metrics for a specific run.

- **WS /ws/live-test**: Connect for live test execution (send JSON config on connect).

- **WS /ws/run/{run_id}**: Subscribe to updates for a queued/background test.

### CLI Mode
Use `load_test.py` for headless testing:

```
python load_test.py --url https://httpbin.org/get --method GET --requests 100 --concurrency 20
```

Outputs summary metrics to console.

## Architecture

- **Frontend**: Static HTML/JS in `/static/` (served at `/`).
- **Backend**: FastAPI (`api_main.py`) handles requests, queuing, and WebSockets.
- **Database**: SQLAlchemy ORM (`models.py`, `database.py`) with TestRun model storing JSON metrics.
- **Load Testing**: Async workers (`load_test.py`) using `httpx` for concurrent requests.
- **Queuing**: RQ + Redis for background jobs (worker updates DB and publishes via Redis Pub/Sub).
- **Deployment**: Dockerfile for Python app; docker-compose.yml orchestrates full stack.

## Metrics Explained
- **Latency (ms)**: Response times with percentiles (p50, p90, etc.) for distribution analysis.
- **RPS**: Requests per second (total requests / total time).
- **Errors**: HTTP 4xx/5xx + transport failures.
- **Timeseries**: Periodic snapshots of progress (every ~0.5s).

## Contributing
1. Fork the repo.
2. Create a feature branch (`git checkout -b feature/amazing-feature`).
3. Commit changes (`git commit -m 'Add amazing feature'`).
4. Push and open a PR.

## Support
- Issues: [GitHub Issues](https://github.com/Zan-Shivam/API-Stress-Lab/issues)
- Author: [@Zan-Shivam](https://github.com/Zan-Shivam)

---

*Built with ❤️ for API warriors. Test hard, fail fast!*
