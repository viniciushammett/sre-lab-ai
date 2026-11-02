import time
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
from opentelemetry.trace import Status, StatusCode
from telemetry import setup_telemetry

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "qwen3:8b"
app = FastAPI(title="AI Platform SRE Lab")
tracer = setup_telemetry(app)
REQUESTS = Counter("ai_inference_requests_total", "Inference requests", ["status"])
TOKENS = Counter("ai_tokens_total", "Tokens", ["type"])
LATENCY = Histogram("ai_inference_duration_seconds", "Inference duration (seconds)")
IN_PROGRESS = Gauge("ai_inference_in_progress", "In-flight inference requests")
for status in ("success", "error"):
    REQUESTS.labels(status=status)
for kind in ("input", "output"):
    TOKENS.labels(type=kind)

class GenerateRequest(BaseModel):
    prompt: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/generate")
async def generate(request: GenerateRequest):
    start = time.perf_counter()
    IN_PROGRESS.inc()
    try:
        with tracer.start_as_current_span("ai.inference") as span:
            span.set_attribute("gen_ai.provider.name", "ollama")
            span.set_attribute("gen_ai.request.model", MODEL)
            span.set_attribute("gen_ai.operation.name", "generate")
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(OLLAMA_URL, json={"model": MODEL, "prompt": request.prompt, "stream": False, "think": False})
                    response.raise_for_status()
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                REQUESTS.labels(status="error").inc()
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR))
                raise HTTPException(status_code=503, detail=f"Ollama unavailable: {exc}") from exc
            data = response.json()
            input_tokens = int(data.get("prompt_eval_count", 0))
            output_tokens = int(data.get("eval_count", 0))
            duration_ms = data.get("total_duration", 0) / 1_000_000
            load_ms = data.get("load_duration", 0) / 1_000_000
            eval_seconds = data.get("eval_duration", 0) / 1_000_000_000
            speed = output_tokens / eval_seconds if eval_seconds > 0 else 0
            TOKENS.labels(type="input").inc(input_tokens)
            TOKENS.labels(type="output").inc(output_tokens)
            REQUESTS.labels(status="success").inc()
            span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
            span.set_attribute("ai.ollama.load_duration_ms", load_ms)
            return {"response": data.get("response", ""), "model": MODEL,
                    "total_duration_ms": round(duration_ms, 2),
                    "load_duration_ms": round(load_ms, 2),
                    "input_tokens": input_tokens, "output_tokens": output_tokens,
                    "tokens_per_second": round(speed, 2)}
    finally:
        LATENCY.observe(time.perf_counter() - start)
        IN_PROGRESS.dec()
