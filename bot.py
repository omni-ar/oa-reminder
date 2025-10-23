import telebot
import requests # <-- Added for HTTP requests
import re
import os # <-- Added to get environment variable

# --- Updated Config Import ---
# Assuming BOT_TOKEN, CHAT_ID, and N8N_EVALUATION_WEBHOOK_URL are in config.py or loaded via dotenv
from config import BOT_TOKEN, CHAT_ID, N8N_EVALUATION_WEBHOOK_URL
# --- Make sure N8N_EVALUATION_WEBHOOK_URL is defined in your config or .env ---
if not N8N_EVALUATION_WEBHOOK_URL:
    raise ValueError("N8N_EVALUATION_WEBHOOK_URL not found in environment/config")
# -----------------------------

from services.problem_fetcher import fetch_problems, fetch_problem_details, load_cache
from services.situational_gen import generate_situational_question_legacy # Using legacy for simplicity here
# --- Removed evaluate_solution import as it's no longer called directly ---

bot = telebot.TeleBot(BOT_TOKEN)

# Command: /start (No change)
@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "👋 Hey Arjit! Use /question to get problems and 'solution qX ...' to submit.")

# Command: /question (Simplified for interactive use - uses legacy situational)
@bot.message_handler(commands=["question"])
def send_question(message):
    try:
        # Use fetch_mixed_problems if available and desired, else fallback
        # For simplicity, using fetch_problems (Codeforces only) here
        problems = fetch_problems(count=2)
        situational = generate_situational_question_legacy() # Get just the string
        text = "📘 Today's Practice Problems:\n\n"

        if not problems:
            text += "⚠️ Couldn't fetch coding problems right now. Try again later.\n\n"
        else:
            for i, p in enumerate(problems, 1):
                platform = f"[{p.get('platform', 'codeforces').upper()}] "
                rating_or_diff = f"(⭐ {p.get('rating')})" if p.get('rating') else f"(⭐ {p.get('difficulty')})"
                text += f"Q{i}: {platform}{p.get('name', 'Unknown')} {rating_or_diff}\n🔗 {p.get('link', 'N/A')}\n\n"

        text += f"Q{len(problems) + 1} (Situational):\n{situational}\n"
        bot.send_message(message.chat.id, text, disable_web_page_preview=True)
    except Exception as e:
        print(f"Error in /question: {e}")
        bot.reply_to(message, "😥 Sorry, couldn't fetch questions right now.")


# Command: /details qX (No change needed for core logic, handles CF only currently)
@bot.message_handler(commands=["details"])
def send_details(message):
    parts = message.text.strip().split()
    if len(parts) != 2 or parts[1].lower() not in ("q1", "q2", "q3", "q4"): # Allow more qkeys potentially
        bot.reply_to(message, "Usage: /details q1 (or q2, q3...)")
        return

    qkey = parts[1].lower()
    cache = load_cache()
    last = cache.get("last_selection", {})
    if qkey not in last:
        bot.reply_to(message, f"No details found for {qkey.upper()}. Run /question first.")
        return

    prob = last[qkey]
    
    # --- Simplified details fetching - only works well for Codeforces ---
    if prob.get("platform") == "codeforces":
        details = fetch_problem_details(prob["contestId"], prob["index"])
        if "error" in details:
            bot.reply_to(message, f"⚠️ Could not fetch details: {details['error']}")
            return

        text = f"📘 Full Details for {qkey.upper()} — {prob['name']} (⭐ {prob['rating']})\n\n"
        text += f"🔗 {prob['link']}\n\n"
        text += f"📖 Statement:\n{details.get('statement', 'Not available')}\n\n"
        if details.get('constraints'):
            text += f"⚙️ Constraints:\n{details['constraints']}\n\n"
        if details.get('samples'):
            for i, s in enumerate(details['samples'], start=1):
                text += f"📝 Sample Input {i}:\n```\n{s.get('input', '')}\n```\n\n"
                text += f"📤 Sample Output {i}:\n```\n{s.get('output', '')}\n```\n\n"
        # --- End CF details ---
    elif prob.get("platform") == "leetcode":
         text = f"📘 Details for LeetCode {qkey.upper()} — {prob['name']} ({prob['difficulty']})\n\n"
         text += f"🔗 {prob['link']}\n\n"
         text += "ℹ️ Full details, constraints, and examples are best viewed on the LeetCode website."
    else:
        text = f"Details for {qkey.upper()} ({prob.get('name', 'Unknown')}) are not available in this format."

    # Split into chunks for Telegram limit
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        try:
            bot.send_message(message.chat.id, chunk, parse_mode='Markdown', disable_web_page_preview=True)
        except Exception as e:
             print(f"Error sending details chunk: {e}")
             # Fallback sending without Markdown if formatting fails
             try:
                 bot.send_message(message.chat.id, chunk, disable_web_page_preview=True)
             except Exception as e2:
                 print(f"Fallback send failed: {e2}")

# --- Removed Daily Reminder & Scheduler ---
# This functionality is handled by the n8n workflow when running the docker-compose setup.
# Keeping it here would cause duplicate messages if both bot.py and n8n are running.

# --- UPDATED Solution Handler ---
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("solution "))
def handle_solution(message):
    """
    Parses the solution message and sends it to the n8n webhook for evaluation.
    """
    text = message.text
    chat_id = message.chat.id
    lines = text.splitlines()

    if len(lines) < 2:
        bot.reply_to(message, "❌ Invalid format. Send as:\nsolution qX [language]\n<code>")
        return

    # Parse first line: "solution qX [language]" (language is optional, defaults to cpp)
    first_line_parts = lines[0].strip().lower().split()
    qkey = None
    language = "cpp" # Default language

    if len(first_line_parts) >= 2:
        if re.match(r"q[1-4]$", first_line_parts[1]):
             qkey = first_line_parts[1]
    if len(first_line_parts) >= 3:
        # Very basic language check, can be improved
        if first_line_parts[2] in ["python", "py", "java", "c++", "cpp", "cxx"]:
             language = first_line_parts[2]
             if language in ["py", "python3"]: language = "python"
             if language in ["c++", "cxx", "cc"]: language = "cpp"

    if not qkey:
        bot.reply_to(message, "❌ Invalid format. Use 'solution qX [language]' on the first line (e.g., solution q1 cpp).")
        return

    code = "\n".join(lines[1:]).strip()
    if not code:
        bot.reply_to(message, "❌ Please paste your code after the first line.")
        return

    # Send immediate feedback to the user
    bot.reply_to(message, f"✅ Got it! Evaluating your {language} solution for {qkey.upper()}...")
    bot.send_chat_action(message.chat.id, "typing")

    # Prepare data payload for n8n webhook
    payload = {
        "qkey": qkey,
        "language": language,
        "code": code, # Send the raw code
        "chat_id": chat_id
    }

    # Send the request to the n8n webhook
    try:
        response = requests.post(N8N_EVALUATION_WEBHOOK_URL, json=payload, timeout=10) # 10 second timeout
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        # Check n8n's response (optional, but good for debugging)
        n8n_response = response.json()
        if n8n_response.get("message") == "Workflow was started":
            print(f"Successfully triggered n8n workflow for {qkey} from chat {chat_id}")
        else:
            print(f"Unexpected response from n8n: {n8n_response}")
            # Don't send an error to user here, as evaluation might still be running

    except requests.exceptions.RequestException as e:
        print(f"❌ Error calling n8n webhook: {e}")
        # Notify user that the submission failed
        bot.send_message(chat_id, f"😥 Sorry, couldn't submit your solution for evaluation right now. Please try again later.\nError: {e}")
    except Exception as e:
        print(f"❌ Unexpected error in handle_solution: {e}")
        bot.send_message(chat_id, "😥 An unexpected error occurred while submitting your solution.")

    # --- IMPORTANT: No response building here ---
    # The n8n workflow is responsible for sending the final evaluation result back to the user.

# --- End UPDATED Solution Handler ---

print("🤖 Bot is running...")
try:
    # Use polling (simple for local testing)
    bot.polling(none_stop=True)
except Exception as e:
    print(f"Bot polling error: {e}")
finally:
    # No scheduler to shutdown now
    print("Bot stopped.")