# services/api_wrapper.py
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import requests
import os
import re # Added for parsing solution messages
import telebot # Added for sending messages back
import logging # Added for better logging

# --- Load Config/Env Vars ---
from dotenv import load_dotenv
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID") # Used for API-triggered actions if needed
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

# Basic Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

if not BOT_TOKEN: raise ValueError("BOT_TOKEN not found")
if not N8N_WEBHOOK_URL: raise ValueError("N8N_WEBHOOK_URL not found")

# Initialize Telegram Bot object (used only for sending replies from API)
# Use threaded=False for better compatibility with FastAPI/Uvicorn
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
logging.info("Telebot instance created.")

# --- Import your service functions ---
from services.problem_fetcher import fetch_mixed_problems, load_cache, fetch_problem_details
from services.situational_gen import generate_situational_question
# evaluator is called via n8n, not directly needed here

app = FastAPI(title="OA Reminder API (Integrated Bot)", version="0.2.0") # Updated title & version

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# --------- API Routes (Endpoints called by n8n or other services) ---------
@app.get("/", tags=["meta"])
def root():
    return {"message": "OA Reminder API (Integrated Bot) is running 🚀", "version": app.version}

@app.get("/health", tags=["meta"])
def health():
    return {"ok": True}

@app.get("/mixed-problems", tags=["problems"])
def get_mixed_problems(count: int = Query(2, ge=1, le=5)):
    logging.info(f"API: Received request for {count} mixed problems.")
    items = fetch_mixed_problems(count=count)
    return {"ok": True, "items": items}

@app.get("/situational", tags=["situational"])
def situational():
    logging.info("API: Received request for situational question.")
    q_dict = generate_situational_question(use_ai=True)
    return {"ok": True, "question": q_dict}

# `/evaluate` endpoint is NOT needed here if all evaluation goes through n8n.
# Keep it ONLY if you need n8n to call back into this API for evaluation logic
# (which is not our current setup). Let's comment it out for clarity.
# @app.post("/evaluate", ...)
# def evaluate(...):
#     ...
# --------- ADD THIS BACK / UNCOMMENT IT ---------
class EvaluateRequest(BaseModel): # Ensure this schema is defined or uncommented
    qkey: str = Field(..., pattern=r"^q[1-4]$", description="q1, q2, q3 or q4") # Updated pattern
    language: str = Field(...) # Removed default, let n8n send it
    code: str = Field(..., min_length=1)

class EvaluateResponse(BaseModel): # Ensure this schema is defined or uncommented
    ok: bool
    problem: Optional[Dict[str, Any]] = None
    results: Optional[List[Dict[str, Any]]] = None
    summary: Optional[str] = None
    compile_error: Optional[str] = None
    error: Optional[str] = None
    # Add fields from your improved evaluator if needed by n8n (like 'note', 'message', 'platform')
    note: Optional[str] = None
    message: Optional[str] = None
    platform: Optional[str] = None
    score: Optional[int] = None


@app.post("/evaluate", response_model=EvaluateResponse, tags=["evaluate"])
def evaluate(req: EvaluateRequest):
    logging.info(f"API: Received request to evaluate {req.language} for {req.qkey}")
    try:
        # We need to import evaluate_solution if it wasn't already
        from services.evaluator import evaluate_solution
        result = evaluate_solution(qkey=req.qkey, language=req.language, code=req.code)
        # Ensure the response matches the EvaluateResponse schema
        # You might need to adjust the schema or the data returned here
        return EvaluateResponse(**result) # Pass the result dict directly if keys match schema
    except Exception as e:
        logging.error(f"Error during /evaluate call: {e}")
        # Return error in the correct schema format
        return EvaluateResponse(ok=False, error=f"Evaluator crashed: {e}")
# --------------------------------------------------


# --- TELEGRAM WEBHOOK HANDLER (Replaces bot.py polling) ---
@app.post("/telegram_bot_webhook/{token}", tags=["telegram"])
async def handle_telegram_update(token: str, request: Request):
    if token != BOT_TOKEN: # Simple security check
         logging.warning("Received webhook call with invalid token.")
         raise HTTPException(status_code=403, detail="Invalid token")

    body = await request.json()
    logging.info(f"Received Telegram update via webhook.")
    # For privacy, avoid logging the full body in production if it contains sensitive info
    # logging.debug(json.dumps(body, indent=2))

    message = body.get("message")
    if not message:
        return {"ok": True, "ignored": "Not a message update"}

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "").strip()

    if not chat_id or not text:
         logging.warning("Webhook received message with missing chat_id or text.")
         return {"ok": True, "ignored": "Missing chat_id or text"}

    # --- Handle '/start' command ---
    if text == "/start":
        logging.info(f"Handling /start command for chat_id: {chat_id}")
        try:
            bot.send_message(chat_id, "👋 Hey there! Use /question to get problems and 'solution qX [lang] ...' to submit code.")
        except Exception as e:
            logging.error(f"Failed to send /start response: {e}")

    # --- Handle '/question' command ---
    elif text == "/question":
        logging.info(f"Handling /question command for chat_id: {chat_id}")
        try:
            bot.send_chat_action(chat_id, "typing")
            problems = fetch_mixed_problems(count=2)
            situational_data = generate_situational_question(use_ai=True)
            reply_text = "📘 Today's Practice Problems:\n\n"

            if not problems:
                reply_text += "⚠️ Couldn't fetch coding problems right now.\n\n"
            else:
                for i, p in enumerate(problems, 1):
                    platform = f"[{p.get('platform', 'unknown').upper()}] "
                    rating_or_diff = f"(⭐ {p.get('rating')})" if p.get('rating') else f"(⭐ {p.get('difficulty')})"
                    reply_text += f"Q{i}: {platform}{p.get('name', 'Unknown')} {rating_or_diff}\n🔗 {p.get('link', 'N/A')}\n\n"

            reply_text += f"Q{len(problems) + 1} (Situational - {situational_data.get('category', 'General')}):\n"
            reply_text += f"{situational_data.get('question', 'Not available')}\n\n"
            reply_text += f"💡 Generated via {situational_data.get('source', 'AI').upper()}"

            bot.send_message(chat_id, reply_text, disable_web_page_preview=True)
        except Exception as e:
            logging.error(f"Error handling /question: {e}")
            try:
                bot.send_message(chat_id, "😥 Sorry, couldn't fetch questions right now.")
            except Exception as e2:
                 logging.error(f"Failed to send error message for /question: {e2}")

    # --- Handle '/details' command ---
    elif text.startswith("/details"):
        logging.info(f"Handling /details command for chat_id: {chat_id}")
        parts = text.split()
        if len(parts) == 2 and re.match(r"q[1-4]$", parts[1].lower()):
            qkey = parts[1].lower()
            try:
                bot.send_chat_action(chat_id, "typing")
                cache = load_cache()
                last = cache.get("last_selection", {})
                if qkey in last:
                    prob = last[qkey]
                    # Simplified response for now, you can add more detail later
                    bot.send_message(chat_id, f"Details for {qkey.upper()} ({prob.get('platform')}: {prob.get('name')})\n🔗 {prob.get('link')}", disable_web_page_preview=True)
                else:
                    bot.send_message(chat_id, f"No details found for {qkey.upper()}. Use /question first.")
            except Exception as e:
                 logging.error(f"Error handling /details: {e}")
                 bot.send_message(chat_id, "😥 Sorry, couldn't fetch details right now.")
        else:
             bot.send_message(chat_id, "Usage: /details q1 (or q2, q3...)")

    # --- Handle 'solution qX...' message ---
    elif text.lower().startswith("/solution "):
        logging.info(f"Handling solution submission for chat_id: {chat_id}")
        lines = text.splitlines()
        if len(lines) < 2:
            bot.send_message(chat_id, "❌ Invalid format. Send as:\nsolution qX [language]\n<code>")
            return {"ok": True, "processed": True}

        first_line_parts = lines[0].strip().lower().split()
        qkey = None
        language = "cpp" # Default

        if len(first_line_parts) >= 2 and re.match(r"q[1-4]$", first_line_parts[1]):
            qkey = first_line_parts[1]
        if len(first_line_parts) >= 3 and first_line_parts[2] in ["python", "py", "java", "c++", "cpp", "cxx"]:
             language = first_line_parts[2]
             if language in ["py", "python3"]: language = "python"
             if language in ["c++", "cxx", "cc"]: language = "cpp"

        if not qkey:
            bot.send_message(chat_id, "❌ Invalid format. Use 'solution qX [language]' on the first line.")
            return {"ok": True, "processed": True}

        code = "\n".join(lines[1:]).strip()
        if not code:
             bot.send_message(chat_id, "❌ Please paste your code after the first line.")
             return {"ok": True, "processed": True}

        # Send to n8n webhook
        try:
            # Acknowledge receipt immediately
            bot.send_message(chat_id, f"✅ Got it! Evaluating your {language} solution for {qkey.upper()} via backend...")
            bot.send_chat_action(chat_id, "typing")
            
            payload = {"qkey": qkey, "language": language, "code": code, "chat_id": chat_id}
            
            logging.info(f"Forwarding evaluation request to n8n webhook for chat_id: {chat_id}, qkey: {qkey}")
            response = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=10) # 10 sec timeout
            response.raise_for_status()
            n8n_response = response.json()
            
            if n8n_response.get("message") == "Workflow was started":
                logging.info(f"Successfully triggered n8n workflow for {qkey} from chat {chat_id}")
            else:
                logging.warning(f"Unexpected response from n8n: {n8n_response}")
                # Don't send error to user, let n8n handle final result/error

        except requests.exceptions.Timeout:
             logging.error(f"Timeout calling n8n webhook for chat_id: {chat_id}")
             bot.send_message(chat_id, f"😥 Sorry, the evaluation request timed out. The backend might be busy. Please try again later.")
        except requests.exceptions.RequestException as e:
            logging.error(f"Error calling n8n webhook: {e}")
            bot.send_message(chat_id, f"😥 Sorry, couldn't submit your solution for evaluation right now.\nError: Connection issue to backend.")
        except Exception as e:
            logging.error(f"Unexpected error in solution handler: {e}")
            bot.send_message(chat_id, "😥 An unexpected error occurred while submitting your solution.")

    # --- Ignore other messages ---
    else:
         logging.info(f"Ignoring non-command message from {chat_id}")

    return {"ok": True, "processed": True} # Acknowledge receipt to Telegram

# --------- Entrypoint (No change here) ---------
if __name__ == "__main__":
    import uvicorn
    logging.info("Starting Uvicorn server locally for development...")
    # reload=True is for development. Remove or set to False for production.
    uvicorn.run("services.api_wrapper:app", host="0.0.0.0", port=8000, reload=True)