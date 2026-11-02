import httpx


def check_health() -> dict:
    url = "http://127.0.0.1:8000/health"
    try:
        response = httpx.get(url, timeout=5.0)
        response.raise_for_status()
        return {"tool": "check_health", "status": "success", "http_status": response.status_code, "data": response.json()}
    except httpx.RequestError as exc:
        return {"tool": "check_health", "status": "error", "error": str(exc)}
    except httpx.HTTPStatusError as exc:
        return {"tool": "check_health", "status": "error", "http_status": exc.response.status_code}


PROMETHEUS_URL = "http://127.0.0.1:9090/api/v1/query"
ALLOWED_METRICS = {
    "successful_inferences": 'sum(ai_inference_requests_total{status="success"})',
    "failed_inferences": 'sum(ai_inference_requests_total{status="error"})',
    "input_tokens": 'sum(ai_tokens_total{type="input"})',
    "output_tokens": 'sum(ai_tokens_total{type="output"})',
}


def query_prometheus(metric: str) -> dict:
    if metric not in ALLOWED_METRICS:
        return {"tool": "query_prometheus", "status": "error", "error": "Metric not allowed"}
    try:
        response = httpx.get(PROMETHEUS_URL, params={"query": ALLOWED_METRICS[metric]}, timeout=5.0)
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "success":
            return {"tool": "query_prometheus", "status": "error", "error": "Prometheus query failed"}
        results = data["data"]["result"]
        if not results:
            return {"tool": "query_prometheus", "status": "no_data", "metric": metric, "value": None}
        return {"tool": "query_prometheus", "status": "success", "metric": metric, "value": float(results[0]["value"][1])}
    except (httpx.RequestError, httpx.HTTPStatusError, KeyError, ValueError, TypeError) as exc:
        return {"tool": "query_prometheus", "status": "error", "error": str(exc)}
