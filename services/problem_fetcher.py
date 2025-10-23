# services/problem_fetcher.py
import requests
import random
import json
import os
import time
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Tuple

CACHE_FILE = "./data/problems_cache.json"
os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)

# Rate limiting to avoid 403 errors
LAST_REQUEST_TIME = 0
MIN_REQUEST_INTERVAL = 2  # seconds between requests

def load_cache():
    """Load cached data from file."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            try:
                data = json.load(f)
                if not isinstance(data, dict):
                    data = {"used_problems": data, "situational_history": []}
                data.setdefault("used_problems", [])
                data.setdefault("situational_history", [])
                data.setdefault("last_selection", {})
                data.setdefault("codeforces_cache", {})
                data.setdefault("leetcode_cache", {})
                return data
            except Exception as e:
                print(f"⚠️ Cache load error: {e}")
                return {"used_problems": [], "situational_history": [], "last_selection": {}, "codeforces_cache": {}, "leetcode_cache": {}}
    return {"used_problems": [], "situational_history": [], "last_selection": {}, "codeforces_cache": {}, "leetcode_cache": {}}

def save_cache(cache):
    """Save cache data to file."""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"⚠️ Cache save error: {e}")

def rate_limit():
    """Implement rate limiting to avoid 403 errors."""
    global LAST_REQUEST_TIME
    current_time = time.time()
    time_since_last = current_time - LAST_REQUEST_TIME
    
    if time_since_last < MIN_REQUEST_INTERVAL:
        sleep_time = MIN_REQUEST_INTERVAL - time_since_last
        print(f"⏱️  Rate limiting: sleeping {sleep_time:.1f}s")
        time.sleep(sleep_time)
    
    LAST_REQUEST_TIME = time.time()

def fetch_codeforces_problems(rating_range=(1200, 1800), count=2, tags=None):
    """Fetch Codeforces problems within rating_range."""
    print("🔍 Fetching Codeforces problems...")
    
    try:
        rate_limit()
        url = "https://codeforces.com/api/problemset.problems"
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Codeforces API error: {e}")
        return []

    if data.get("status") != "OK":
        print(f"❌ Codeforces API returned error: {data.get('comment', 'Unknown')}")
        return []

    problems = data["result"]["problems"]
    
    filtered = [p for p in problems if "rating" in p and rating_range[0] <= p["rating"] <= rating_range[1]]
    
    if tags:
        filtered = [p for p in filtered if any(tag in p.get("tags", []) for tag in tags)]

    cache = load_cache()
    used = cache.get("used_problems", [])
    fresh = [p for p in filtered if f"cf_{p['contestId']}{p['index']}" not in used]
    
    if not fresh:
        print("ℹ️  All problems used, resetting history")
        fresh = filtered
        used = []

    if len(fresh) < count:
        print(f"⚠️ Only {len(fresh)} problems available (requested {count})")
        count = len(fresh)

    selected = random.sample(fresh, min(count, len(fresh)))

    result = []
    for p in selected:
        contestId = p["contestId"]
        index = p["index"]
        result.append({
            "name": p["name"], "rating": p["rating"], "link": f"https://codeforces.com/problemset/problem/{contestId}/{index}",
            "contestId": contestId, "index": index, "tags": p.get("tags", []), "platform": "codeforces"
        })

    used.extend([f"cf_{p['contestId']}{p['index']}" for p in selected])
    cache["used_problems"] = used
    
    last = {}
    for i, p in enumerate(result, start=1):
        key = f"q{i}"
        last[key] = {
            "name": p["name"], "rating": p["rating"], "link": p["link"], "contestId": p["contestId"],
            "index": p["index"], "platform": "codeforces"
        }
    cache["last_selection"] = last
    save_cache(cache)

    for i, p in enumerate(result, start=1):
        p["qkey"] = f"q{i}"

    print(f"✅ Fetched {len(result)} Codeforces problems")
    return result

def fetch_codeforces_details(contestId, index, use_cache=True):
    """Scrape full problem details from Codeforces with caching."""
    cache_key = f"cf_{contestId}{index}"
    cache = load_cache()
    
    if use_cache and cache_key in cache.get("codeforces_cache", {}):
        print(f"📦 Using cached details for {contestId}{index}")
        return cache["codeforces_cache"][cache_key]
    
    print(f"🌐 Fetching details for Codeforces {contestId}{index}")
    
    url = f"https://codeforces.com/problemset/problem/{contestId}/{index}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        rate_limit()
        res = requests.get(url, headers=headers, timeout=15)
        
        if res.status_code == 403: return {"error": f"Problem {contestId}{index} blocked (403). Try again in a few minutes."}
        if res.status_code == 404: return {"error": f"Problem {contestId}{index} not found (404)."}
        if res.status_code != 200: return {"error": f"HTTP {res.status_code} for problem {contestId}{index}"}
            
    except requests.exceptions.RequestException as e:
        return {"error": f"Network error: {e}"}

    soup = BeautifulSoup(res.text, "html.parser")
    statement_div = soup.find("div", class_="problem-statement")
    if not statement_div:
        return {"error": f"Problem {contestId}{index} details could not be parsed."}

    statement_text = statement_div.get_text("\n", strip=True)
    
    input_spec = soup.find("div", class_="input-specification")
    output_spec = soup.find("div", class_="output-specification")
    constraints = ""
    if input_spec: constraints += "Input:\n" + input_spec.get_text("\n", strip=True) + "\n"
    if output_spec: constraints += "Output:\n" + output_spec.get_text("\n", strip=True)

    samples = []
    for inp, out in zip(soup.find_all("div", class_="input"), soup.find_all("div", class_="output")):
        input_text = inp.get_text("\n", strip=True).replace("Input\n", "").replace("input\n", "")
        output_text = out.get_text("\n", strip=True).replace("Output\n", "").replace("output\n", "")
        samples.append({"input": input_text.strip(), "output": output_text.strip()})

    skeletons = {
        "cpp": f"#include <bits/stdc++.h>\nusing namespace std;\n\nvoid solve() {{\n    // Your code here\n}}\n\nint main() {{\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n    solve();\n    return 0;\n}}",
        "python": f"def solve():\n    # Your code here\n    pass\n\nif __name__ == \"__main__\":\n    solve()",
        "java": f"import java.util.*;\nimport java.io.*;\n\npublic class Solution {{\n    public static void solve() {{\n        // Your code here\n    }}\n    \n    public static void main(String[] args) {{\n        solve();\n    }}\n}}"
    }

    result = {
        "statement": statement_text, "constraints": constraints.strip(), "samples": samples,
        "skeletons": skeletons, "link": url, "platform": "codeforces"
    }
    
    if "codeforces_cache" not in cache: cache["codeforces_cache"] = {}
    cache["codeforces_cache"][cache_key] = result
    save_cache(cache)
    
    print(f"✅ Cached details for {contestId}{index}")
    return result

def fetch_leetcode_problems(difficulty="Medium", count=2, tags=None):
    """Fetch LeetCode problems using the public GraphQL API (FREE!)."""
    print(f"🔍 Fetching LeetCode {difficulty} problems...")
    
    url = "https://leetcode.com/graphql"
    query = """
    query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
        problemsetQuestionList: questionList(categorySlug: $categorySlug, limit: $limit, skip: $skip, filters: $filters) {
            questions: data { questionId, questionFrontendId, title, titleSlug, difficulty, topicTags { name, slug }, isPaidOnly }
        }
    }
    """
    
    # --- THIS IS THE FIX: Add randomness to the skip parameter ---
    random_skip = random.randint(0, 500)
    variables = {"categorySlug": "", "limit": 50, "skip": random_skip, "filters": {"difficulty": difficulty.upper()}}
    # -----------------------------------------------------------
    
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    
    try:
        rate_limit()
        response = requests.post(url, json={"query": query, "variables": variables}, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ LeetCode API error: {e}")
        return []
    
    if "errors" in data:
        print(f"❌ LeetCode GraphQL error: {data['errors']}")
        return []
    
    problems = data.get("data", {}).get("problemsetQuestionList", {}).get("questions", [])
    problems = [p for p in problems if not p.get("isPaidOnly", False)]
    
    if tags:
        problems = [p for p in problems if any(tag.lower() in [t["slug"] for t in p.get("topicTags", [])] for tag in tags)]
    
    cache = load_cache()
    used = cache.get("used_problems", [])
    fresh = [p for p in problems if f"lc_{p['questionFrontendId']}" not in used]
    
    if not fresh:
        print("ℹ️  All LeetCode problems used, resetting")
        fresh = problems
        used = []
    
    if len(fresh) < count: count = len(fresh)
    
    selected = random.sample(fresh, min(count, len(fresh)))
    
    result = []
    for p in selected:
        result.append({
            "name": p["title"], "difficulty": p["difficulty"], "link": f"https://leetcode.com/problems/{p['titleSlug']}/",
            "questionId": p["questionFrontendId"], "titleSlug": p["titleSlug"], "tags": [tag["name"] for tag in p.get("topicTags", [])], "platform": "leetcode"
        })
    
    used.extend([f"lc_{p['questionId']}" for p in selected])
    cache["used_problems"] = used
    
    last = cache.get("last_selection", {})
    for i, p in enumerate(result, start=1):
        last[f"q{i}"] = {
            "name": p["name"], "difficulty": p["difficulty"], "link": p["link"], "questionId": p["questionId"],
            "titleSlug": p["titleSlug"], "platform": "leetcode"
        }
    cache["last_selection"] = last
    save_cache(cache)
    
    for i, p in enumerate(result, start=1):
        p["qkey"] = f"q{i}"
    
    print(f"✅ Fetched {len(result)} LeetCode problems")
    return result

# Updated mixed fetcher to ensure cache consistency

def fetch_mixed_problems(count=2, cf_rating=(1200, 1800), lc_difficulty="Medium"):
    """
    Fetch a mix of Codeforces and LeetCode problems, ensuring cache consistency.
    """
    cf_count = count // 2
    lc_count = count - cf_count
    
    problems = []
    
    # Fetch problems (these functions save their own partial cache, which is okay)
    try:
        cf_problems = fetch_codeforces_problems(rating_range=cf_rating, count=cf_count)
        problems.extend(cf_problems)
    except Exception as e:
        print(f"⚠️ Codeforces fetch failed: {e}")
    
    try:
        lc_problems = fetch_leetcode_problems(difficulty=lc_difficulty, count=lc_count)
        problems.extend(lc_problems)
    except Exception as e:
        print(f"⚠️ LeetCode fetch failed: {e}")
    
    # If we didn't get the desired count, try fetching more from Codeforces as backup
    if len(problems) < count:
        needed = count - len(problems)
        print(f"ℹ️ Fetching {needed} more Codeforces problems as backup.")
        try:
            backup_cf = fetch_codeforces_problems(rating_range=cf_rating, count=needed)
            problems.extend(backup_cf)
        except Exception as e:
            print(f"⚠️ Backup Codeforces fetch failed: {e}")

    # Shuffle the final list
    random.shuffle(problems)
    
    # Ensure we only return the requested number of problems
    problems = problems[:count]
    
    # --- THIS IS THE FIX ---
    # Reassign qkeys AND update the final last_selection cache
    cache = load_cache()
    last = {}
    for i, p in enumerate(problems, start=1):
        qkey = f"q{i}"
        p["qkey"] = qkey # Update the problem dict itself
        
        # Save the detailed info needed by the evaluator to the cache
        if p.get("platform") == "codeforces":
            last[qkey] = {
                "name": p["name"], "rating": p.get("rating"), "link": p["link"],
                "contestId": p["contestId"], "index": p["index"], "platform": "codeforces"
            }
        elif p.get("platform") == "leetcode":
             last[qkey] = {
                "name": p["name"], "difficulty": p.get("difficulty"), "link": p["link"],
                "questionId": p.get("questionId"), "titleSlug": p["titleSlug"], "platform": "leetcode"
            }
        # Add other platforms if needed
            
    cache["last_selection"] = last
    save_cache(cache)
    print(f"✅ Updated last_selection cache with {len(last)} mixed problems.")
    # -----------------------
    
    return problems

# Backward compatible wrappers
def fetch_problems(rating_range=(1200, 1800), count=2):
    return fetch_codeforces_problems(rating_range, count)

def fetch_problem_details(contestId, index):
    return fetch_codeforces_details(contestId, index)

if __name__ == "__main__":
    print("Testing Problem Fetcher\n" + "="*70)
    
    print("\n🔵 Testing Codeforces:")
    cf_problems = fetch_codeforces_problems(count=2, tags=['dp'])
    for p in cf_problems:
        print(f"  - [{p['qkey']}] {p['name']} (Rating: {p['rating']})")
        print(f"    {p['link']}")
        fetch_codeforces_details(p['contestId'], p['index'])
    
    print("\n🟢 Testing LeetCode:")
    lc_problems = fetch_leetcode_problems(difficulty="Medium", count=2, tags=['array'])
    for p in lc_problems:
        print(f"  - [{p['qkey']}] {p['name']} ({p['difficulty']})")
        print(f"    {p['link']}")
    
    print("\n🟣 Testing Mixed:")
    mixed = fetch_mixed_problems(count=4)
    for p in mixed:
        print(f"  - [{p['qkey']}] [{p['platform'].upper()}] {p['name']}")
    
    print("\n" + "="*70)
    print("✅ All tests complete!")