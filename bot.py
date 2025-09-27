import telebot
from apscheduler.schedulers.background import BackgroundScheduler
from config import BOT_TOKEN, CHAT_ID
from services.problem_fetcher import fetch_problems, fetch_problem_details, load_cache
from services.situational_gen import generate_situational_question
import re
from services.evaluator import evaluate_solution

bot = telebot.TeleBot(BOT_TOKEN)

# Command: /start
@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "👋 Hey Arjit! I'll remind you daily at 9 PM with new OA problems!")

# Command: /question
@bot.message_handler(commands=["question"])
def send_question(message):
    problems = fetch_problems()
    situational = generate_situational_question()
    text = "📘 Today's Practice Problems:\n\n"

    for i, p in enumerate(problems, 1):
        details = fetch_problem_details(p["contestId"], p["index"])
        text += f"Q{i}: {p['name']} (⭐ {p['rating']})\n🔗 {p['link']}\n\n"
        if "error" not in details:
            text += f"📖 Statement:\n{details['statement'][:500]}...\n"
            if details["samples"]:
                sample = details["samples"][0]
                text += f"📝 Sample Input:\n{sample['input']}\n📤 Sample Output:\n{sample['output']}\n\n"
            text += f"💻 Signature: {details['signature']}\n\n"

    text += f"Q3 (Situational):\n{situational}\n"
    bot.send_message(message.chat.id, text)

# Command: /details q1|q2
@bot.message_handler(commands=["details"])
def send_details(message):
    parts = message.text.strip().split()
    if len(parts) != 2 or parts[1].lower() not in ("q1", "q2"):
        bot.reply_to(message, "Usage: /details q1 OR /details q2")
        return

    qkey = parts[1].lower()
    cache = load_cache()
    last = cache.get("last_selection", {})
    if qkey not in last:
        bot.reply_to(message, f"No details found for {qkey.upper()}. Run /question first.")
        return

    prob = last[qkey]
    details = fetch_problem_details(prob["contestId"], prob["index"])
    if "error" in details:
        bot.reply_to(message, f"⚠️ Could not fetch details: {details['error']}")
        return

    text = f"📘 Full Details for {qkey.upper()} — {prob['name']} (⭐ {prob['rating']})\n\n"
    text += f"🔗 {prob['link']}\n\n"
    text += f"📖 Statement:\n{details['statement']}\n\n"
    if details["constraints"]:
        text += f"⚙️ Constraints:\n{details['constraints']}\n\n"

    if details["samples"]:
        for i, s in enumerate(details["samples"], start=1):
            text += f"📝 Sample Input {i}:\n{s['input']}\n\n"
            text += f"📤 Sample Output {i}:\n{s['output']}\n\n"

    text += f"💻 Suggested Function Signature:\n{details['signature']}\n\n"

    # Split into chunks for Telegram limit
    for chunk in [text[i:i+3500] for i in range(0, len(text), 3500)]:
        bot.send_message(message.chat.id, chunk)

# Daily Reminder
def daily_reminder():
    problems = fetch_problems()
    situational = generate_situational_question()
    text = "⏰ Daily OA Reminder (9 PM)!\n\n"
    for i, p in enumerate(problems, 1):
        details = fetch_problem_details(p["contestId"], p["index"])
        text += f"Q{i}: {p['name']} (⭐ {p['rating']})\n🔗 {p['link']}\n\n"
        if "error" not in details:
            text += f"📖 {details['statement'][:500]}...\n\n"
    text += f"Q3 (Situational):\n{situational}\n"
    bot.send_message(CHAT_ID, text)

# Scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(daily_reminder, "cron", hour=21, minute=0)  # 9:00 PM IST
scheduler.start()

# Solution Handler
@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("solution "))
def handle_solution(message):
    """
    Expected:
    solution q1
    <cpp code>
    """
    text = message.text
    lines = text.splitlines()
    if not lines:
        bot.reply_to(message, "Send as:\nsolution q1\n<your C++ code>")
        return

    # First line like: "solution q1" or "solution q2"
    first = lines[0].strip().lower()
    m = re.match(r"solution\s+(q1|q2)\s*$", first)
    if not m:
        bot.reply_to(message, "Use 'solution q1' or 'solution q2' on the first line, then paste your C++ code.")
        return

    qkey = m.group(1)
    code = "\n".join(lines[1:]).strip()
    if not code:
        bot.reply_to(message, "Please paste your C++ code after the first line.")
        return

    bot.send_chat_action(message.chat.id, "typing")
    result = evaluate_solution(qkey=qkey, language="cpp", code=code)

    if not result.get("ok"):
        err = result.get("error") or result.get("compile_error") or "Unknown error"
        bot.reply_to(message, f"❌ Evaluation failed:\n{err}")
        return

    # Build response
    resp = [f"🧪 Evaluation for {qkey.upper()} — {result['problem']['name']}"]
    resp.append(result["summary"])

    for r in result["results"]:
        if r.get("ok"):
            resp.append(f"✅ Case {r['case']}")
        elif r.get("timeout"):
            resp.append(f"⏳ Case {r['case']}: Timed out")
        else:
            exp = r['expected'].strip().replace("\r", "")
            got = r['got'].strip().replace("\r", "")
            resp.append(f"❌ Case {r['case']}:\nExpected:\n{exp[:300]}\nGot:\n{got[:300]}")

    bot.reply_to(message, "\n\n".join(resp))

print("🤖 Bot is running...")
try:
    bot.polling(none_stop=True)
finally:
    scheduler.shutdown()
