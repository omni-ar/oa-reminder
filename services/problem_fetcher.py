import requests
import random
import json
import os
from bs4 import BeautifulSoup

CACHE_FILE = "./data/problems_cache.json"
os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            try:
                data = json.load(f)
                if not isinstance(data, dict):
                    data = {"used_problems": data, "situational_history": []}
                data.setdefault("used_problems", [])
                data.setdefault("situational_history", [])
                data.setdefault("last_selection", {})
                return data
            except Exception:
                return {"used_problems": [], "situational_history": [], "last_selection": {}}
    return {"used_problems": [], "situational_history": [], "last_selection": {}}


def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def fetch_problems(rating_range=(1200, 1800), count=2):
    """
    Fetch Codeforces problems within rating_range.
    Returns a list of dicts with metadata.
    Also saves 'last_selection' in cache for evaluator.
    """
    url = "https://codeforces.com/api/problemset.problems"
    res = requests.get(url).json()
    if res.get("status") != "OK":
        return []

    problems = res["result"]["problems"]
    filtered = [p for p in problems if "rating" in p and rating_range[0] <= p["rating"] <= rating_range[1]]

    cache = load_cache()
    used = cache.get("used_problems", [])

    fresh = [p for p in filtered if f"{p['contestId']}{p['index']}" not in used]
    if not fresh:
        fresh = filtered
        used = []

    selected = random.sample(fresh, min(count, len(fresh)))

    result = []
    for p in selected:
        contestId = p["contestId"]
        index = p["index"]
        link = f"https://codeforces.com/problemset/problem/{contestId}/{index}"
        result.append({
            "name": p["name"],
            "rating": p["rating"],
            "link": link,
            "contestId": contestId,
            "index": index
        })

    used.extend([f"{p['contestId']}{p['index']}" for p in selected])
    cache["used_problems"] = used

    last = {}
    for i, p in enumerate(result, start=1):
        key = f"q{i}"
        last[key] = {
            "name": p["name"],
            "rating": p["rating"],
            "link": p["link"],
            "contestId": p["contestId"],
            "index": p["index"]
        }
    cache["last_selection"] = last
    save_cache(cache)

    for i, p in enumerate(result, start=1):
        p["qkey"] = f"q{i}"

    return result


def fetch_problem_details(contestId, index):
    """
    Scrape full problem details (statement, constraints, samples) from Codeforces.
    """
    url = f"https://codeforces.com/problemset/problem/{contestId}/{index}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        res = requests.get(url, headers=headers, timeout=10)
    except Exception as e:
        return {"error": f"Network error fetching problem {contestId}{index}: {e}"}

    if res.status_code == 403:
        return {"error": f"Problem {contestId}{index} blocked by Codeforces (403 Forbidden). Try again later."}
    if res.status_code == 404:
        return {"error": f"Problem {contestId}{index} is no longer available on Codeforces."}
    if res.status_code != 200:
        return {"error": f"Unexpected error ({res.status_code}) fetching problem {contestId}{index}"}


    soup = BeautifulSoup(res.text, "html.parser")

    statement_div = soup.find("div", class_="problem-statement")
    if not statement_div:
        return {"error": f"Problem {contestId}{index} exists but details could not be parsed."}

    statement_text = statement_div.get_text("\n", strip=True)

    input_spec = soup.find("div", class_="input-specification")
    output_spec = soup.find("div", class_="output-specification")
    constraints = ""
    if input_spec:
        constraints += "Input:\n" + input_spec.get_text("\n", strip=True) + "\n"
    if output_spec:
        constraints += "Output:\n" + output_spec.get_text("\n", strip=True)

    samples = []
    sample_inputs = soup.find_all("div", class_="input")
    sample_outputs = soup.find_all("div", class_="output")
    for inp, out in zip(sample_inputs, sample_outputs):
        samples.append({
            "input": inp.get_text("\n", strip=True).replace("Input\n", ""),
            "output": out.get_text("\n", strip=True).replace("Output\n", "")
        })

    signature = "void solve()"
    skeleton = f"""#include <bits/stdc++.h>
using namespace std;

{signature} {{
    // your code here
}}

int main(){{
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    solve();
    return 0;
}}"""

    return {
        "statement": statement_text,
        "constraints": constraints.strip(),
        "samples": samples,
        "signature": signature,
        "skeleton": skeleton,
        "link": url
    }

