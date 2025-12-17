# api_main.py
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, HttpUrl, Field
from typing import Literal, List, Any, Dict
from sqlalchemy.orm import Session
from rq import Queue
import asyncio
import json
import os
from load_test import run_load_test
from database import Base, engine, SessionLocal
from models import TestRun
from redis import Redis


Base.metadata.create_all(bind=engine)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="API Stress Lab")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_conn = Redis.from_url(REDIS_URL, decode_responses=True)
rq_queue = Queue("load-tests", connection=redis_conn)
redis_sub = redis_conn


class LoadTestRequest(BaseModel):
    url: HttpUrl
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"] = "GET"
    total_requests: int = Field(ge=1, le=1000, default=50)
    concurrency: int = Field(ge=1, le=200, default=10)
    label: str | None = None


class TestRunSummary(BaseModel):
    id: int
    url: HttpUrl
    method: str
    total_requests: int
    concurrency: int
    created_at: Any  # keep simple for now
    label: str | None = None

    class Config:
        orm_mode = True


class TestRunDetail(BaseModel):
    id: int
    url: HttpUrl
    method: str
    total_requests: int
    concurrency: int
    created_at: Any
    metrics: Dict[str, Any]
    label: str | None = None

    class Config:
        orm_mode = True


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def index():
    file_path = os.path.join(BASE_DIR, "static", "index.html")
    return FileResponse(file_path)


@app.post("/run-test", response_model=TestRunDetail)
async def run_test(payload: LoadTestRequest, db: Session = Depends(get_db)):
    """
    Enqueue a background load test job and return the TestRun record.
    The actual load test will run in a worker process (tasks.run_test_job).
    """
    # 1) create DB record immediately so client gets a run_id
    t = TestRun(
        url=str(payload.url),
        method=payload.method,
        total_requests=payload.total_requests,
        concurrency=payload.concurrency,
        label=payload.label,
        metrics_json=json.dumps({"status": "queued"}),
    )
    db.add(t)
    db.commit()
    db.refresh(t)

    run_id = t.id

    # 2) enqueue the job to RQ (worker will pick it up)
    rq_queue.enqueue(
        "tasks.run_test_job",
        run_id,
        str(payload.url),
        payload.method,
        payload.total_requests,
        payload.concurrency,
        job_timeout=60 * 60,
    )

    # 3) return summary (client should open WS /ws/run/{run_id} to receive progress)
    return TestRunDetail(
        id=t.id,
        url=t.url,
        method=t.method,
        total_requests=t.total_requests,
        concurrency=t.concurrency,
        created_at=t.created_at,
        metrics={"status": "queued"},
        label=t.label,
    )


@app.get("/tests", response_model=List[TestRunSummary])
def list_tests(db: Session = Depends(get_db)):
    runs = db.query(TestRun).order_by(TestRun.created_at.desc()).all()
    return runs


@app.get("/tests/{test_id}", response_model=TestRunDetail)
def get_test(test_id: int, db: Session = Depends(get_db)):
    t = db.query(TestRun).filter(TestRun.id == test_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Test run not found")

    metrics = json.loads(t.metrics_json)
    return TestRunDetail(
        id=t.id,
        url=t.url,
        method=t.method,
        total_requests=t.total_requests,
        concurrency=t.concurrency,
        created_at=t.created_at,
        metrics=metrics,
    )


@app.websocket("/ws/live-test")
async def websocket_live_test(ws: WebSocket):
    await ws.accept()
    db = SessionLocal()
    test_run = None

    try:
        
        data = await ws.receive_json()
        url = data["url"]
        method = data.get("method", "GET")
        total_requests = int(data.get("total_requests", 20))
        concurrency = int(data.get("concurrency", 5))
        label = data.get("label")  # optional, if you added label earlier

        
        test_run = TestRun(
            url=url,
            method=method,
            total_requests=total_requests,
            concurrency=concurrency,
            label=label if hasattr(TestRun, "label") else None,
            metrics_json="{}",
        )
        db.add(test_run)
        db.commit()
        db.refresh(test_run)

        run_id = test_run.id

        
        async def progress_callback(progress: dict):
            await ws.send_json(
                {
                    "type": "progress",
                    "run_id": run_id,
                    **progress,  # completed, total
                }
            )

        
        metrics = await run_load_test(
            url=url,
            method=method,
            total_requests=total_requests,
            concurrency=concurrency,
            progress_callback=progress_callback,
        )

        
        test_run.metrics_json = json.dumps(metrics)
        db.add(test_run)
        db.commit()

       
        await ws.send_json(
            {
                "type": "done",
                "run_id": run_id,
                "metrics": metrics,
            }
        )

    except WebSocketDisconnect:
        # client closed the connection
        return
    except Exception as e:
        # unexpected error; try to notify client
        try:
            await ws.send_json(
                {
                    "type": "error",
                    "message": str(e),
                }
            )
        except Exception:
            pass
    finally:
        await ws.close()
        db.close()



@app.websocket("/ws/run/{run_id}")
async def ws_run_updates(ws: WebSocket, run_id: int):
    await ws.accept()

    try:
        pubsub = redis_sub.pubsub(ignore_subscribe_messages=True)
        channel = f"run:{run_id}"
        pubsub.subscribe(channel)

        loop = asyncio.get_event_loop()

        # On connect, send the current DB snapshot so clients that connect late catch up
        db = SessionLocal()
        try:
            tr = db.query(TestRun).filter(TestRun.id == run_id).first()
            if tr:
                try:
                    snapshot = json.loads(tr.metrics_json or "{}")
                except Exception:
                    snapshot = {}
                await ws.send_json({"type": "snapshot", "run_id": run_id, "metrics": snapshot})
        finally:
            db.close()

        # Poll pubsub.get_message() in a thread so it doesn't block the event loop.
        while True:
            msg = await loop.run_in_executor(None, lambda: pubsub.get_message(timeout=1.0))
            if msg:
                payload = msg.get("data")
                if payload:
                    # payload is JSON string from tasks.publish; forward as-is
                    try:
                        await ws.send_text(payload)
                    except Exception:
                        break
            await asyncio.sleep(0.01)

    except WebSocketDisconnect:
        return
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            pubsub.unsubscribe(channel)
            pubsub.close()
        except Exception:
            pass
        await ws.close()



