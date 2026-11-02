# AI Platform SRE Lab

## Conteúdo

- `main.py`: FastAPI `/health`, `/generate`, `/metrics` com Ollama e Prometheus.
- `telemetry.py`: instrumentação OpenTelemetry da API.
- `agent/agent.py`: chat interativo com Qwen3 e tool calling.
- `agent/tools.py`: `check_health` e `query_prometheus` com consultas predefinidas.
- `agent/telemetry.py`: instrumentação da conversa, LLM e ferramentas.
- `prometheus/prometheus.yml`: scrape da API via Docker.
- `docker-compose.yml`: Jaeger, Prometheus, Grafana.

## Pré-requisitos

WSL2 Ubuntu com Python 3.12, Docker Engine + plugin `docker compose`, Ollama em funcionamento com modelo `qwen3:8b` (`ollama pull qwen3:8b`).

## Inicialização

```bash
cd sre-lab-ai-reconstruido
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Verificar docker compose config antes de iniciar
./start-ai-lab.sh
curl http://127.0.0.1:8000/health
python -m agent.agent
```

Jaeger: http://localhost:16686 — Prometheus: http://localhost:9090 — Grafana: http://localhost:3000.

**Nota de rede:** `host.docker.internal` com `host-gateway` depende da configuração Docker/WSL. Para Prometheus alcançar FastAPI, Uvicorn escuta em `0.0.0.0:8000`.

## Exemplo de teste de inferência

```bash
curl -sS -X POST http://127.0.0.1:8000/generate -H 'Content-Type: application/json' -d '{"prompt":"Explain SRE in one sentence."}'
```

## Segurança / escopo

As ferramentas são somente leitura e PromQL é uma whitelist. Não exponha as portas diretamente à internet. Grafana usa credenciais iniciais da imagem e deve ser configurado antes de qualquer exposição.
