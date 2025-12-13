from prometheus_client import Counter, Histogram, generate_latest
from fastapi import Request, Response
from time import time
import os
SERVICE_NAME = os.getenv("SERVICE_NAME", "unknown_service")
REQUEST_COUNT = Counter("requests_total","Total API requests",["service","endpoint","method","status"])
REQUEST_LATENCY = Histogram("request_latency_seconds","Request latency (s)",["service","endpoint","method"])
async def metrics_middleware(request: Request, call_next):
    t0=time(); resp=await call_next(request); dt=time()-t0
    ep=request.url.path
    REQUEST_COUNT.labels(SERVICE_NAME,ep,request.method,resp.status_code).inc()
    REQUEST_LATENCY.labels(SERVICE_NAME,ep,request.method).observe(dt)
    return resp
def metrics_endpoint(): return Response(generate_latest(), media_type="text/plain")
