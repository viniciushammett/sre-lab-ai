from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor


def setup_telemetry(app):
    resource = Resource.create({"service.name": "ai-platform-sre-lab", "service.version": "1.0.0", "deployment.environment.name": "local"})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint="http://127.0.0.1:4318/v1/traces")))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    return trace.get_tracer("ai-platform-sre-lab")
