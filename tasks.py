# tasks.py
import json
import asyncio
from redis import Redis
from database import SessionLocal
from models import TestRun
from load_test import run_load_test
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis = Redis.from_url(REDIS_URL, decode_responses=True)

def publish(run_id: int, payload: dict):
    channel = f"run:{run_id}"
    redis.publish(channel, json.dumps(payload))


def worker_progress_callback(run_id: int):
   
    async def _cb(progress: dict):
        
        publish(run_id, {"type": "progress", "run_id": run_id, **progress})

        db = SessionLocal()
        try:
            tr = db.query(TestRun).filter(TestRun.id == run_id).first()
            if tr:
                try:
                    metrics = json.loads(tr.metrics_json or "{}")
                except Exception:
                    metrics = {}
                metrics.setdefault("progress", {})
                metrics["progress"].update(progress)
                tr.metrics_json = json.dumps(metrics)
                db.add(tr)
                db.commit()
        finally:
            db.close()

    return _cb

def run_test_job(run_id: int, url: str, method: str, total_requests: int, concurrency: int):
    
    progress_cb = worker_progress_callback(run_id)

    result  = asyncio.run(
        run_load_test(
            url=url,
            method=method,
            total_requests=total_requests,
            concurrency=concurrency,
            progress_callback=progress_cb,
        )
    )

    db = SessionLocal()
    try:
        tr = db.query(TestRun).filter(TestRun.id == run_id).first()
        if tr:
            tr.metrics_json = json.dumps(result)
            db.add(tr)
            db.commit()
    finally:
        db.close()

    publish(run_id, {"type": "done", "run_id": run_id, "metrics": result})
