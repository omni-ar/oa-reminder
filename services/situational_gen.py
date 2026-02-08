# services/situational_gen.py
import random
import json
import os
from datetime import datetime
from transformers import pipeline
from transformers import T5Tokenizer, T5ForConditionalGeneration
import torch

CACHE_FILE = "./data/problems_cache.json"
os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)

generator = None
model = None
tokenizer = None

def get_generator():
    """Load T5 model explicitly for text generation."""
    global generator, model, tokenizer
    
    if generator is None:
        print("💡 Loading Flan-T5 model for interview questions...")
        try:
            model_name = "google/flan-t5-base"
            
            # Load model and tokenizer manually
            tokenizer = T5Tokenizer.from_pretrained(model_name)
            model = T5ForConditionalGeneration.from_pretrained(
                model_name,
                torch_dtype=torch.float32,
                low_cpu_mem_usage=True
            )
            
            # Wrapper function to act like a generator
            def generate_text(prompt, max_length=150):
                inputs = tokenizer(prompt, return_tensors="pt", max_length=512, truncation=True)
                outputs = model.generate(
                    **inputs,
                    max_length=max_length,
                    do_sample=True,
                    temperature=0.8,
                    top_p=0.9,
                    num_return_sequences=1
                )
                return tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            generator = generate_text
            print("✅ Flan-T5 model loaded successfully.")
            
        except Exception as e:
            print(f"⚠️ Flan-T5 load failed: {e}")
            generator = None
    
    return generator

# Enhanced question bank with multiple categories
QUESTION_BANK = {
    "system_design": [
        "Design a URL shortener handling 1000 requests/second with 99.9% uptime.",
        "How would you architect a real-time chat system for 10M concurrent users?",
        "Design a distributed cache with automatic failover and data replication.",
        "How would you build a rate limiter for an API gateway processing 100K req/s?",
        "Design a notification system supporting email, SMS, and push notifications.",
        "How would you design a video streaming service like YouTube?",
        "Design a ride-sharing system like Uber with real-time location tracking.",
        "How would you build a scalable e-commerce platform handling Black Friday traffic?",
        "Design a search autocomplete system for 1M products with sub-100ms latency.",
        "How would you architect a distributed job scheduler processing 1M tasks daily?",
    ],
    "algorithms": [
        "Find the longest substring without repeating characters in O(n) time.",
        "Implement an LRU cache with O(1) get and put operations.",
        "Design an algorithm to detect cycles in a linked list without extra space.",
        "How would you merge K sorted arrays with minimal space complexity?",
        "Find all anagrams of a pattern in a given string efficiently.",
        "Implement a function to find the kth largest element in an unsorted array.",
        "How would you design a data structure for a browser's back/forward buttons?",
        "Find the minimum window substring containing all characters of a pattern.",
        "Implement a binary search tree with insert, delete, and search in O(log n).",
        "Design an algorithm to flatten a multi-level linked list.",
    ],
    "debugging": [
        "Your database queries became 10x slower overnight. How do you investigate?",
        "Memory usage keeps increasing in production despite no new deployments. Debug this.",
        "API latency spikes every hour at exactly the same time. What's your approach?",
        "Users report random 500 errors you can't reproduce locally. How do you debug?",
        "Your service times out when calling a third-party API. How do you handle this?",
        "Production logs show null pointer exceptions but only for 2% of requests. Debug it.",
        "A microservice becomes unresponsive after running for 24 hours. What do you check?",
        "Your database connection pool is exhausted during peak hours. How do you fix it?",
        "CPU usage jumps to 100% when processing specific user requests. How do you debug?",
        "Your application works fine in staging but crashes in production. Debug this.",
    ],
    "architecture": [
        "How would you migrate a monolith to microservices with zero downtime?",
        "Design a payment system ensuring exactly-once transaction processing.",
        "How do you handle API versioning for millions of users without breaking changes?",
        "Design a logging system processing 1TB of logs per day with real-time search.",
        "How would you implement feature flags for gradual rollouts to 10M users?",
        "Design a multi-tenant SaaS application with data isolation and shared infrastructure.",
        "How would you architect a real-time analytics dashboard processing streaming data?",
        "Design an event-driven architecture for order processing in an e-commerce system.",
        "How would you implement circuit breakers and retry logic in a microservices system?",
        "Design a backup and disaster recovery strategy for a critical financial system.",
    ],
    "behavioral": [
        "Describe a time you made a technical decision with incomplete information.",
        "How did you handle a situation where your team strongly disagreed with your approach?",
        "Tell me about a production incident you caused and how you resolved it.",
        "Describe how you convinced stakeholders to adopt a new but risky technology.",
        "How do you balance technical debt with delivering new features?",
        "Tell me about a time you had to debug a critical issue under extreme pressure.",
        "Describe a situation where you had to learn a new technology very quickly.",
        "How did you handle a conflict between two senior engineers on your team?",
        "Tell me about a project that failed and what you learned from it.",
        "Describe how you mentored a junior developer who was struggling.",
    ],
    "performance": [
        "Your API serves 1M req/day. Optimize for 10M without adding servers.",
        "Database queries take 5 seconds. What optimization strategies would you try?",
        "How would you reduce a React app bundle size from 5MB to 500KB?",
        "Your background job queue has a 2-hour backlog. How do you fix this?",
        "Page load time is 8 seconds. Walk me through your optimization process.",
        "Your Redis cache hit rate dropped from 90% to 30%. How do you investigate?",
        "An SQL query scanning 10M rows takes 30 seconds. How do you optimize it?",
        "Your API's P99 latency is 5 seconds while P50 is 100ms. What's wrong?",
        "Your application uses 8GB RAM for processing 100KB of data. How do you fix this?",
        "A Docker image takes 10 minutes to build. How would you optimize the build time?",
    ],
    "coding_practices": [
        "How do you ensure code quality in a fast-paced startup environment?",
        "Explain your approach to writing unit tests for a complex legacy codebase.",
        "How would you implement CI/CD for a monorepo with 50 microservices?",
        "What's your strategy for conducting effective code reviews without blocking the team?",
        "How do you handle secret management and API keys in a cloud-native application?",
        "Describe your approach to refactoring a 10-year-old codebase without breaking it.",
        "How would you implement comprehensive logging without impacting performance?",
        "What's your strategy for maintaining API backwards compatibility across versions?",
        "How do you ensure database migrations don't cause downtime in production?",
        "Describe your approach to implementing observability in a distributed system.",
    ],
}

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

def get_question_from_bank(force_random=False):
    """Get a unique question from the question bank using date-based rotation."""
    cache = load_cache()
    history = cache.get("situational_history", [])
    
    # Use date as seed for consistency, unless forcing random for a test
    if not force_random:
        today = datetime.now().strftime("%Y-%m-%d")
        random.seed(today)
    
    # Rotate through categories based on day of year
    day_of_year = datetime.now().timetuple().tm_yday
    categories = list(QUESTION_BANK.keys())
    category = categories[day_of_year % len(categories)]
    
    # Get questions from selected category
    questions = QUESTION_BANK[category]
    
    # Filter out recently asked questions
    available_questions = [q for q in questions if q not in history[-20:]]
    
    if not available_questions:
        # If all questions from the category were used recently, reset and use all from that category
        available_questions = questions
    
    question = random.choice(available_questions)
    
    return question, category

def generate_ai_question_with_context():
    """Generate a question using AI with question bank as inspiration."""
    gen = get_generator()
    if not gen:
        return None
    
    try:
        day_of_year = datetime.now().timetuple().tm_yday
        categories = list(QUESTION_BANK.keys())
        category = categories[day_of_year % len(categories)]
        example_questions = random.sample(QUESTION_BANK[category], min(3, len(QUESTION_BANK[category])))
        examples_text = "\n".join([f"- {q}" for q in example_questions])
        
        contexts = ["for an e-commerce platform", "for a social media app", "for a fin-tech system", "for a streaming service"]
        context = contexts[day_of_year % len(contexts)]
        
        prompt = (
            f"Act as a senior software engineer conducting an interview. Your task is to ASK a challenging "
            f"{category.replace('_', ' ')} question related to {context}.\n\n"
            f"Follow these examples for style:\n{examples_text}\n\n"
            f"RULES:\n"
            f"1. ASK a direct question to the candidate. It must be a real interview question.\n"
            f"2. DO NOT ask questions ABOUT interviews (e.g., 'What is a good question...').\n"
            f"3. The question MUST be under 35 words and end with a question mark.\n\n"
            f"Ask the question now:"
        )
        
        # ✅ FIXED: gen() now returns string directly
        text = gen(prompt, max_length=100)
        text = text.strip().replace("Question:", "").strip()
        
        if not text.endswith("?"):
            text += "?"
            
        if len(text) < 20 or len(text) > 300:
            return None
            
        return text, category
    
    except Exception as e:
        print(f"⚠️ AI generation failed: {e}")
        return None

def generate_situational_question(use_ai=True, max_retries=3):
    """Generate a situational question using AI with question bank as fallback."""
    cache = load_cache()
    history = cache.get("situational_history", [])
    
    question = None
    category = "mixed"
    source = "bank"
    
    if use_ai:
        for attempt in range(max_retries):
            result = generate_ai_question_with_context()
            if result:
                question, category = result
                source = "ai"
                
                if question not in history[-15:]:
                    print(f"✅ AI generated unique question (attempt {attempt + 1})")
                    break
                else:
                    print(f"⚠️ AI generated duplicate, retrying... (attempt {attempt + 1})")
                    question = None
            else:
                print(f"⚠️ AI generation failed (attempt {attempt + 1})")
    
    if not question:
        print("📚 Using question bank as fallback")
        question, category = get_question_from_bank()
        source = "bank"
    
    attempts = 0
    while question in history[-10:] and attempts < 5:
        print(f"⚠️ Question in recent history, getting alternative... (attempt {attempts + 1})")
        # For uniqueness, always fall back to the larger bank with a random seed
        question, category = get_question_from_bank(force_random=True)
        source = "bank"
        attempts += 1
    
    history.append(question)
    if len(history) > 100:
        history = history[-100:]
    
    cache["situational_history"] = history
    save_cache(cache)
    
    return {
        "question": question,
        "category": category.replace("_", " ").title(),
        "source": source,
        "date": datetime.now().strftime("%Y-%m-%d"),
    }

def generate_situational_question_legacy():
    """Legacy function that returns just the question string for backward compatibility."""
    result = generate_situational_question(use_ai=False)
    return result["question"]

# if __name__ == "__main__":
#     print("Testing Hybrid AI + Question Bank Generator\n" + "="*70)
    
#     print("\n🤖 Testing AI Generation with Question Bank Context:")
#     print("-" * 70)
    
#     for i in range(3):
#         result = generate_situational_question(use_ai=True, max_retries=2)
#         print(f"\n{i+1}. Category: {result['category']}")
#         print(f"   Source: {result['source']}")
#         print(f"   Question: {result['question']}")
    
#     print("\n" + "="*70)
#     print("\n📚 Testing Question Bank Fallback:")
#     print("-" * 70)
    
#     for i in range(2):
#         result = generate_situational_question(use_ai=False)
#         print(f"\n{i+1}. Category: {result['category']}")
#         print(f"   Source: {result['source']}")
#         print(f"   Question: {result['question']}")
    
#     print("\n" + "="*70)
#     print("✅ Question generation test complete!")