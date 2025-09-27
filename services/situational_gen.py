# services/situational_gen.py
import random
import json
import os
from transformers import pipeline

CACHE_FILE = "./data/problems_cache.json"
os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)

# ---- CHANGE 1: Define generator as None initially ----
generator = None

def get_generator():
    """
    This function initializes the model the first time it's called
    and then reuses the loaded model on subsequent calls.
    """
    global generator
    if generator is None:
        print("💡 Loading situational question generator model for the first time...")
        try:
            generator = pipeline(
                "text2text-generation",
                model="google/flan-t5-base",
                device=-1  # CPU only
            )
            print("✅ Model loaded successfully.")
        except Exception as e:
            print(f"⚠️ Could not load transformers model: {e}")
            # Keep generator as None so we can fall back to seed questions
    return generator

seed_questions = [
    "You are designing an online exam system for 10,000 students. How would you ensure no cheating happens?",
    "How would you design an elevator system for a 50-floor building with 10 elevators?",
    "You are tasked with designing a chat app like WhatsApp. How would you handle billions of messages per day?",
    "How would you scale a food delivery app during peak dinner hours?",
    "If you are a team lead and one member is underperforming, how would you handle it?"
]

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    return {"situational_history": data}
                return data
            except Exception:
                return {"situational_history": []}
    return {"situational_history": []}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

def generate_situational_question():
    cache = load_cache()
    history = cache.get("situational_history", [])

    question = None
    
    # ---- CHANGE 2: Call our new function to get the generator ----
    gen = get_generator()

    if gen:
        try:
            prompt = (
                "Generate ONE concise interview-style question for a software engineer. "
                "It should be either:\n"
                "1. A technical system design question (scalability, reliability, performance, debugging), OR\n"
                "2. A behavioral/situational question (teamwork, leadership, problem solving).\n"
                "Do NOT generate meta-questions about interviews themselves. "
                "Keep it under 25 words and end with a question mark."
            )

            result = gen(
                prompt,
                max_new_tokens=80,
                do_sample=True,
                temperature=0.7,
                top_p=0.9
            )
            text = result[0]["generated_text"].strip()
            if not text.endswith("?"):
                text += "?"
            question = text[:200]
        except Exception as e:
            print(f"⚠️ Local generation failed: {e}")

    if not question:
        print("Falling back to seed question.")
        question = random.choice(seed_questions)

    if question in history:
        return generate_situational_question()

    history.append(question)
    if len(history) > 7:
        history.pop(0)

    cache["situational_history"] = history
    save_cache(cache)

    return question