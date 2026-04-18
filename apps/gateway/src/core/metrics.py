from prometheus_fastapi_instrumentator import Instrumentator
from fastapi import FastAPI

instrumentator = Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    should_instrument_requests_inprogress=True,
    inprogress_name="inprogress",
    inprogress_labels=True,
)

def setup_metrics(app: FastAPI):
    instrumentator.instrument(app).expose(app, endpoint="/api/v1/metrics")
