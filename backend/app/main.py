from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.forms.registry import get_form
from app.models import AsyncRequest, AsyncResult, EvaluationRequest, FormOutput

app = FastAPI(title="Executable Forms Prototype")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/forms/{form_id}/evaluate", response_model=FormOutput)
def evaluate_form(form_id: str, request: EvaluationRequest) -> FormOutput:
    form = get_form(form_id)
    if form is None:
        raise HTTPException(status_code=404, detail=f"Unknown form: {form_id}")

    return form.evaluate(request.state, request.context, request.async_results)


@app.post("/forms/{form_id}/async-requests/resolve", response_model=AsyncResult)
def resolve_async_request(form_id: str, request: AsyncRequest) -> AsyncResult:
    form = get_form(form_id)
    if form is None:
        raise HTTPException(status_code=404, detail=f"Unknown form: {form_id}")

    try:
        return form.resolve_async_request(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
