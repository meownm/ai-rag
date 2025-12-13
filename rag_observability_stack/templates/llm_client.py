import os, time
from prometheus_client import Histogram, Counter
from langchain_community.llms import OpenAI
SERVICE_NAME=os.getenv("SERVICE_NAME","unknown_service")
LLM_LATENCY=Histogram("llm_latency_seconds","LLM response time",["service","model","endpoint"])
TOKENS_TOTAL=Counter("tokens_total","Total tokens",["service","model","endpoint"])
def get_llm():
    endpoint=os.getenv("LLM_ENDPOINT", f"http://localhost:{os.getenv('HELICONE_PORT','8787')}/v1/completions")
    model=os.getenv("LLM_MODEL","gpt-oss:20b")
    class MonitoredLLM(OpenAI):
        def _call(self, prompt, stop=None):
            t0=time.time(); out=super()._call(prompt, stop=stop)
            LLM_LATENCY.labels(SERVICE_NAME,model,"LLM_call").observe(time.time()-t0)
            TOKENS_TOTAL.labels(SERVICE_NAME,model,"LLM_call").inc(max(1,len(out.split())))
            return out
    return MonitoredLLM(model=model, base_url=endpoint, headers={"Helicone-Auth": os.getenv("HELICONE_API_KEY","local-dev")})
