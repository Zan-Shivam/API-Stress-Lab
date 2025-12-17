import argparse
import asyncio
from collections.abc import Awaitable, Callable
import time
from collections import Counter
from statistics import mean
from typing import List, Tuple
import httpx

def percentile(latencies: List[float], p: float) -> float:
    if not latencies:
        return 0.0
    latencies_sorted = sorted(latencies)
    k = (len(latencies_sorted) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(latencies_sorted) - 1)
    if f == c:
        return latencies_sorted[f]
    d0 = latencies_sorted[f] * (c - k)
    d1 = latencies_sorted[c] * (k - f)
    return d0 + d1


async def worker(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    semaphore: asyncio.Semaphore,
    results: List[Tuple[float, int, bool]],
    state: dict,
    total_requests: int,
    timeseries: list,
    progress_callback: Callable[[dict], Awaitable[None]] | None = None,
):
    async with semaphore:
        start = time.perf_counter()
        status_code = None
        is_transport_error = False

        try:
            resp = await client.request(method=method, url=url, timeout=10.0)
            elapsed_ms = (time.perf_counter() - start) * 1000
            status_code = resp.status_code
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            is_transport_error = True

        
        results.append((elapsed_ms, status_code, is_transport_error))

        # update shared completed count
        state["completed"] += 1

        if progress_callback is not None:
            latencies_so_far = [r[0] for r in results]
            http_errors_so_far = sum(
                1 for r in results
                if r[1] is not None and r[1] >= 400
            )

            avg_latency = (
                    sum(latencies_so_far) / len(latencies_so_far)
                    if latencies_so_far
                    else 0.0
                )
            
            now = time.time()
            if not timeseries or (now - timeseries[-1]["timestamp"]) >= 0.5:
                timeseries.append({
                    "timestamp": now,
                    "completed": state["completed"],
                    "avg_latency_ms": round(avg_latency, 2),
                    "errors": http_errors_so_far,
                })

            await progress_callback(
                    {
                        "type": "progress",
                        "completed": state["completed"],
                        "total": total_requests,
                        "avg_latency_ms": round(avg_latency, 2),
                        "errors": http_errors_so_far,
                        "timestamp": time.time(),
                    }
                )

async def run_load_test(
    url: str,
    method: str = "GET",
    total_requests: int = 50,
    concurrency: int = 10,
    progress_callback: Callable[[dict], Awaitable[None]] | None = None,
):
    semaphore = asyncio.Semaphore(concurrency)
    results: List[Tuple[float, int, bool]] = []
    timeseries: list[dict] = []


    start_time = time.perf_counter()

    state = {"completed": 0}

    start_time = time.perf_counter()

    async with httpx.AsyncClient() as client:
        tasks = [
            worker(
                client,
                method,
                url,
                semaphore,
                results,
                state,
                total_requests,
                timeseries,
                progress_callback,
            )
            for _ in range(total_requests)
        ]
        await asyncio.gather(*tasks)

    total_time = time.perf_counter() - start_time

    latencies = [r[0] for r in results]
    
    http_results = [r for r in results if r[1] is not None]
    transport_errors = [r for r in results if r[2]]
    status_codes = [r[1] for r in http_results]
    successes = [r for r in http_results if r[1] < 400]
    http_failures = [r for r in http_results if r[1] >= 400]


    total = len(results)
    success_count = len(successes)
    failure_count = len(http_failures) + len(transport_errors)


    avg_latency = mean(latencies) if latencies else 0.0
    min_latency = min(latencies) if latencies else 0.0
    max_latency = max(latencies) if latencies else 0.0

    p50 = percentile(latencies, 50)
    p90 = percentile(latencies, 90)
    p95 = percentile(latencies, 95)
    p99 = percentile(latencies, 99)

    rps = total / total_time if total_time > 0 else 0.0

    status_dist = Counter(status_codes)

    metrics = {
        "total_time_seconds": total_time,
        "total_requests": total,
        "successful_requests": success_count,
        "failed_requests": failure_count,
        "transport_errors": len(transport_errors),
        "requests_per_second": rps,
        "latency_ms": {
            "avg": avg_latency,
            "min": min_latency,
            "max": max_latency,
            "p50": p50,
            "p90": p90,
            "p95": p95,
            "p99": p99,
        },
        "status_codes": dict(status_dist),
    }

    return {
    "summary": metrics,
    "timeseries": timeseries,
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Simple API load test tool")
    parser.add_argument("--url", required=True, help="Target URL")
    parser.add_argument("--method", default="GET", help="HTTP method (default: GET)")
    parser.add_argument(
        "--requests",
        type=int,
        default=50,
        help="Total number of requests to send (default: 50)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Number of concurrent workers (default: 10)",
    )
    return parser.parse_args()

async def debug_progress(p: dict):
    print(f"Progress: {p['completed']} / {p['total']}")


def main():
    args = parse_args()
    metrics = asyncio.run(
        run_load_test(
            url=args.url,
            method=args.method.upper(),
            total_requests=args.requests,
            concurrency=args.concurrency,
            progress_callback=debug_progress,
        )
    )

    
    print("\n=== Load Test Results ===")
    print(f"Total time          : {metrics['total_time_seconds']:.2f} s")
    print(f"Total requests      : {metrics['total_requests']}")
    print(f"Successful          : {metrics['successful_requests']}")
    print(f"Failed              : {metrics['failed_requests']}")
    print(f"Requests per second : {metrics['requests_per_second']:.2f} req/s\n")

    lat = metrics["latency_ms"]
    print("Latency (ms):")
    print(f"  avg : {lat['avg']:.2f}")
    print(f"  min : {lat['min']:.2f}")
    print(f"  max : {lat['max']:.2f}")
    print(f"  p50 : {lat['p50']:.2f}")
    print(f"  p90 : {lat['p90']:.2f}")
    print(f"  p95 : {lat['p95']:.2f}")
    print(f"  p99 : {lat['p99']:.2f}\n")

    print("Status codes:")
    if metrics["status_codes"]:
        for code, count in metrics["status_codes"].items():
            print(f"  {code}: {count}")
    else:
        print("  (no successful responses)")

    print("\nDone.\n")



if __name__ == "__main__":
    main()
