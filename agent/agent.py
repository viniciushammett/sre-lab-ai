import asyncio
import json
import httpx
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Status, StatusCode
from agent.tools import check_health, query_prometheus
from agent.telemetry import configure_agent_telemetry

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL_NAME = "qwen3:8b"
MAX_AGENT_STEPS = 5
TOOLS = [
    {"type": "function", "function": {"name": "check_health", "description": "Check whether the AI platform FastAPI health endpoint is responding.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "query_prometheus", "description": "Query real monitoring metrics from Prometheus: inferences, errors, token consumption.", "parameters": {"type": "object", "properties": {"metric": {"type": "string", "enum": ["successful_inferences", "failed_inferences", "input_tokens", "output_tokens"], "description": "Approved metric name"}}, "required": ["metric"]}}}
]
AVAILABLE_TOOLS = {"check_health": check_health, "query_prometheus": query_prometheus}
tracer = configure_agent_telemetry()

async def execute_tool(tool_call):
    fn = tool_call["function"]["name"]
    args = tool_call["function"].get("arguments", {})
    with tracer.start_as_current_span(f"agent.tool.{fn}") as span:
        span.set_attribute("agent.tool.name", fn)
        if fn not in AVAILABLE_TOOLS:
            result = {"tool": fn, "status": "error", "error": "Unauthorized tool"}
        else:
            try:
                if not isinstance(args, dict):
                    raise ValueError("Tool arguments must be an object")
                if fn == "check_health":
                    if args:
                        raise ValueError("check_health does not accept arguments")
                    result = await asyncio.to_thread(check_health)
                elif fn == "query_prometheus":
                    if set(args) != {"metric"} or not isinstance(args["metric"], str):
                        raise ValueError("query_prometheus requires a metric")
                    result = await asyncio.to_thread(query_prometheus, args["metric"])
            except Exception as exc:
                span.record_exception(exc)
                result = {"tool": fn, "status": "error", "error": str(exc)}
        span.set_attribute("agent.tool.status", result.get("status", "unknown"))
        if result.get("status") == "error":
            span.set_status(Status(StatusCode.ERROR))
        print(f"\n[TOOL] {fn}")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        tool_message = {"role": "tool", "tool_name": fn, "content": json.dumps(result)}
        if tool_call.get("id"):
            tool_message["tool_call_id"] = tool_call["id"]
        return tool_message

async def run_turn(client, messages):
    with tracer.start_as_current_span("agent.conversation_turn") as span:
        span.set_attribute("agent.name", "sre-incident-investigator")
        span.set_attribute("agent.model", MODEL_NAME)
        for _ in range(MAX_AGENT_STEPS):
            with tracer.start_as_current_span("agent.llm.chat") as llm_span:
                llm_span.set_attribute("gen_ai.operation.name", "chat")
                llm_span.set_attribute("gen_ai.provider.name", "ollama")
                llm_span.set_attribute("gen_ai.request.model", MODEL_NAME)
                response = await client.post(OLLAMA_URL, json={"model": MODEL_NAME, "messages": messages, "tools": TOOLS, "stream": False, "think": False})
                response.raise_for_status()
                data = response.json()
                llm_span.set_attribute("gen_ai.usage.input_tokens", data.get("prompt_eval_count", 0))
                llm_span.set_attribute("gen_ai.usage.output_tokens", data.get("eval_count", 0))
            assistant_message = data["message"]
            messages.append(assistant_message)
            tool_calls = assistant_message.get("tool_calls", [])
            if not tool_calls:
                print(f"\nQwen: {assistant_message.get('content', '')}\n")
                span.set_attribute("agent.outcome", "completed")
                return
            for call in tool_calls:
                messages.append(await execute_tool(call))
        span.set_attribute("agent.outcome", "step_limit")
        print("\n[AGENT] Limite de etapas atingido.\n")

async def main():
    print("\n========================================")
    print("       SRE AI AGENT — Qwen3 8B")
    print("========================================")
    print("Digite 'sair' para encerrar.\n")
    messages = [{"role": "system", "content": "You are a conversational SRE investigation agent. Respond in Brazilian Portuguese. Use tools to obtain actual infrastructure data, never invent monitoring results, and base conclusions on evidence. A health endpoint confirms API responsiveness, not all dependencies. Approved tools are read-only."}]
    async with httpx.AsyncClient(timeout=120.0) as client:
        while True:
            try:
                user_input = input("Você: ").strip()
            except (KeyboardInterrupt, EOFError):
                break
            if user_input.lower() in ("sair", "exit", "quit"):
                break
            if not user_input:
                continue
            messages.append({"role": "user", "content": user_input})
            # Snapshot: avoid retaining an incomplete tool-call exchange after errors.
            snapshot = len(messages)
            try:
                await run_turn(client, messages)
            except Exception as exc:
                del messages[snapshot:]
                print(f"\n[ERRO] {exc}\n")
    print("\nEncerrando SRE AI Agent.\n")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        provider = trace.get_tracer_provider()
        if isinstance(provider, TracerProvider):
            provider.force_flush()
            provider.shutdown()
