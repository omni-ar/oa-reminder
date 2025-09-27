# services/api_wrapper.py
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import requests
import os

from services.problem_fetcher import (
    fetch_problems,
    fetch_problem_details,
    load_cache,
)
from services.situational_gen import generate_situational_question
from services.evaluator import evaluate_solution

# Load env vars if needed
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="OA Reminder API", version="0.1.0")

# Allow n8n / external clients to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------- Schemas ---------
class EvaluateRequest(BaseModel):
    qkey: str = Field(..., pattern=r"^q[12]$", description="q1 or q2")
    language: str = Field("cpp", description="Only 'cpp' supported currently")
    code: str = Field(..., min_length=1)

class EvaluateResponse(BaseModel):
    ok: bool
    problem: Optional[Dict[str, Any]] = None
    results: Optional[List[Dict[str, Any]]] = None
    summary: Optional[str] = None
    compile_error: Optional[str] = None
    error: Optional[str] = None

# --------- Routes ---------
@app.get("/", tags=["meta"])
def root():
    return {"message": "OA Reminder API is running 🚀", "version": app.version}

@app.get("/health", tags=["meta"])
def health():
    return {"ok": True}

@app.get("/problems", tags=["problems"])
def get_problems(
    min_rating: int = Query(1200, ge=800, le=3500),
    max_rating: int = Query(1800, ge=800, le=3500),
    count: int = Query(2, ge=1, le=5),
    include_full: bool = Query(
        False, description="If true, try to include statement/samples (may 403 on Codeforces)"
    ),
):
    items = fetch_problems((min_rating, max_rating), count)
    if include_full:
        enriched = []
        for p in items:
            details = fetch_problem_details(p["contestId"], p["index"])
            if "error" in details:
                p["details_error"] = details["error"]
            else:
                p["statement"] = details.get("statement")
                p["constraints"] = details.get("constraints")
                p["samples"] = details.get("samples")
                p["signature"] = details.get("signature")
                p["skeleton"] = details.get("skeleton")
            enriched.append(p)
        return {"ok": True, "items": enriched}
    return {"ok": True, "items": items}

@app.get("/last_selection", tags=["problems"])
def last_selection():
    cache = load_cache()
    return {"ok": True, "last_selection": cache.get("last_selection", {})}

@app.get("/details/{qkey}", tags=["problems"])
def details_for_qkey(qkey: str):
    qkey = qkey.lower()
    if qkey not in ("q1", "q2"):
        raise HTTPException(status_code=400, detail="qkey must be q1 or q2")
    cache = load_cache()
    last = cache.get("last_selection", {})
    if qkey not in last:
        raise HTTPException(status_code=404, detail=f"No {qkey.upper()} in last selection. Call /problems first.")
    prob = last[qkey]
    details = fetch_problem_details(prob["contestId"], prob["index"])
    if "error" in details:
        raise HTTPException(status_code=502, detail=details["error"])
    return {"ok": True, "problem": prob, "details": details}

@app.get("/details/by-id", tags=["problems"])
def details_by_id(contestId: int = Query(...), index: str = Query(...)):
    details = fetch_problem_details(contestId, index)
    if "error" in details:
        raise HTTPException(status_code=502, detail=details["error"])
    return {"ok": True, "contestId": contestId, "index": index, "details": details}

@app.get("/situational", tags=["situational"])
def situational():
    q = generate_situational_question()
    return {"ok": True, "question": q}

@app.post("/evaluate", response_model=EvaluateResponse, tags=["evaluate"])
def evaluate(req: EvaluateRequest):
    if req.language != "cpp":
        raise HTTPException(status_code=400, detail="Only 'cpp' is supported right now.")
    try:
        result = evaluate_solution(qkey=req.qkey, language=req.language, code=req.code)
    except Exception as e:
        return EvaluateResponse(ok=False, error=f"Evaluator crashed: {e}")

    if not result.get("ok"):
        return EvaluateResponse(
            ok=False,
            problem=result.get("problem"),
            results=result.get("results"),
            summary=result.get("summary") or "Evaluation failed (maybe samples unavailable).",
            compile_error=result.get("compile_error"),
            error=result.get("error"),
        )

    return EvaluateResponse(
        ok=True,
        problem=result.get("problem"),
        results=result.get("results"),
        summary=result.get("summary"),
        compile_error=result.get("compile_error"),
        error=result.get("error"),
    )

# --------- Telegram → n8n bridge ---------
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/evaluate-solution")

@app.post("/telegram_webhook", tags=["telegram"])
async def telegram_webhook(request: Request):
    body = await request.json()
    message = body.get("message", {}).get("text", "")
    chat_id = body.get("message", {}).get("chat", {}).get("id")

    if not message:
        return {"ok": True, "ignored": True}

    # Command: /evaluate <code>
    if message.startswith("/evaluate"):
        code = message[len("/evaluate "):]

        # Forward to n8n webhook
        try:
            resp = requests.post(N8N_WEBHOOK_URL, json={"code": code, "chat_id": chat_id})
            return {"ok": True, "forwarded": resp.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return {"ok": True, "ignored": True}

# --------- Entrypoint ---------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.api_wrapper:app", host="0.0.0.0", port=8000, reload=True)
