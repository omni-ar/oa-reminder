import os
import re
import json
import subprocess
import tempfile
import shutil
import time
from bs4 import BeautifulSoup
import requests
from typing import List, Tuple, Dict, Optional

CACHE_FILE = "./data/problems_cache.json"
SUBMISSIONS_DIR = "./submissions"
os.makedirs(SUBMISSIONS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)

# Playwright optional
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️ Playwright not installed. Using requests for scraping.")


def _load_cache():
    """Load cached data."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}


def _save_cache(cache):
    """Save cache data."""
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def _normalize(s: str) -> str:
    """Normalize output."""
    lines = [ln.rstrip() for ln in s.strip().splitlines()]
    return "\n".join(lines).strip()


def _fetch_codeforces_samples_playwright(problem_url: str) -> List[Tuple[str, str]]:
    """Scrape Codeforces using Playwright."""
    if not PLAYWRIGHT_AVAILABLE:
        return []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            page.goto(problem_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1)
            html_content = page.content()
            browser.close()
            return _parse_codeforces_samples(html_content)
    except Exception as e:
        print(f"⚠️ Playwright scraping failed: {e}")
        return []


def _fetch_codeforces_samples_requests(problem_url: str) -> List[Tuple[str, str]]:
    """Scrape Codeforces using requests."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        time.sleep(1)
        response = requests.get(problem_url, headers=headers, timeout=15)
        if response.status_code != 200:
            return []
        return _parse_codeforces_samples(response.text)
    except Exception as e:
        print(f"⚠️ Requests scraping failed: {e}")
        return []


def _parse_codeforces_samples(html_content: str) -> List[Tuple[str, str]]:
    """Parse sample test cases from Codeforces HTML."""
    soup = BeautifulSoup(html_content, "lxml")
    sample_tests = soup.find_all("div", class_="sample-test")
    if not sample_tests:
        return []
    
    pairs = []
    for block in sample_tests:
        inputs = block.select("div.input pre")
        outputs = block.select("div.output pre")
        for inp, out in zip(inputs, outputs):
            def extract_text(pre):
                txt = "".join(
                    str(x) if isinstance(x, str) else ("\n" if x.name == "br" else x.get_text())
                    for x in pre.contents
                )
                return txt.strip()
            pairs.append((extract_text(inp), extract_text(out)))
    return pairs


def _fetch_codeforces_samples(problem_url: str, use_cache=True) -> List[Tuple[str, str]]:
    """Fetch sample tests from Codeforces with caching."""
    cache = _load_cache()
    sample_cache = cache.get("sample_cache", {})
    
    if use_cache and problem_url in sample_cache:
        print(f"📦 Using cached samples for {problem_url}")
        return [tuple(pair) for pair in sample_cache[problem_url]]
    
    print(f"🌐 Fetching samples from {problem_url}")
    samples = []
    if PLAYWRIGHT_AVAILABLE:
        samples = _fetch_codeforces_samples_playwright(problem_url)
    if not samples:
        samples = _fetch_codeforces_samples_requests(problem_url)
    
    if samples:
        sample_cache[problem_url] = samples
        cache["sample_cache"] = sample_cache
        _save_cache(cache)
        print(f"✅ Cached {len(samples)} sample tests")
    
    return samples


def _fetch_leetcode_samples(problem_slug: str, use_cache=True) -> List[Tuple[str, str]]:
    """Fetch sample test cases from LeetCode."""
    cache = _load_cache()
    sample_cache = cache.get("sample_cache", {})
    cache_key = f"lc_{problem_slug}"
    
    if use_cache and cache_key in sample_cache:
        print(f"📦 Using cached LeetCode samples")
        return [tuple(pair) for pair in sample_cache[cache_key]]
    
    print(f"🌐 Fetching LeetCode samples for {problem_slug}")
    url = "https://leetcode.com/graphql"
    query = """
    query questionData($titleSlug: String!) {
        question(titleSlug: $titleSlug) {
            exampleTestcases
        }
    }
    """
    
    try:
        time.sleep(1)
        response = requests.post(
            url,
            json={"query": query, "variables": {"titleSlug": problem_slug}},
            headers={"Content-Type": "application/json"},
            timeout=15
        )
        data = response.json()
        question_data = data.get("data", {}).get("question", {})
        example_tests = question_data.get("exampleTestcases", "")
        
        if not example_tests:
            return []
        
        lines = example_tests.strip().split("\n")
        samples = [(lines[i], lines[i + 1]) for i in range(0, len(lines) - 1, 2)]
        
        if samples:
            sample_cache[cache_key] = samples
            cache["sample_cache"] = sample_cache
            _save_cache(cache)
        
        return samples
    except Exception as e:
        print(f"⚠️ LeetCode fetch failed: {e}")
        return []


def _write_code_to_file(code: str, path: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)


def _compile_cpp(source_path: str, exe_path: str):
    cmd = ["g++", "-std=c++17", "-O2", source_path, "-o", exe_path]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
    return proc.returncode, proc.stdout, proc.stderr


def _run_cpp(exe_path: str, input_data: str, timeout_sec: int = 3):
    proc = subprocess.run(exe_path, input=input_data, stdout=subprocess.PIPE, 
                         stderr=subprocess.PIPE, text=True, timeout=timeout_sec)
    return proc.returncode, proc.stdout, proc.stderr


def _run_python(source_path: str, input_data: str, timeout_sec: int = 5):
    proc = subprocess.run(["python", source_path], input=input_data, 
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout_sec)
    return proc.returncode, proc.stdout, proc.stderr


def _compile_java(source_path: str, class_dir: str):
    cmd = ["javac", "-d", class_dir, source_path]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
    return proc.returncode, proc.stdout, proc.stderr


def _run_java(class_dir: str, class_name: str, input_data: str, timeout_sec: int = 5):
    proc = subprocess.run(["java", "-cp", class_dir, class_name], input=input_data,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout_sec)
    return proc.returncode, proc.stdout, proc.stderr


def evaluate_cpp_solution(qkey: str, code: str, samples: List[Tuple[str, str]], tmpdir: str):
    source_path = os.path.join(tmpdir, f"{qkey}.cpp")
    exe_path = os.path.join(tmpdir, f"{qkey}.exe") if os.name == "nt" else os.path.join(tmpdir, qkey)
    _write_code_to_file(code, source_path)
    
    rc, out, err = _compile_cpp(source_path, exe_path)
    if rc != 0:
        return {"ok": False, "summary": "Compilation failed", "compile_error": err[:2000], "results": []}
    
    results = []
    passed = 0
    for idx, (inp, expected) in enumerate(samples, start=1):
        try:
            rc2, got_out, got_err = _run_cpp(exe_path, inp, timeout_sec=3)
            got_norm = _normalize(got_out)
            exp_norm = _normalize(expected)
            ok = (rc2 == 0) and (got_norm == exp_norm)
            if ok:
                passed += 1
            results.append({
                "case": idx, "ok": ok, "exit_code": rc2,
                "input": inp[:1000], "expected": expected[:1000],
                "got": got_out[:1000], "stderr": got_err[:500] if got_err else ""
            })
        except subprocess.TimeoutExpired:
            results.append({
                "case": idx, "ok": False, "timeout": True,
                "input": inp[:1000], "expected": expected[:1000],
                "got": "", "stderr": "Time Limit Exceeded"
            })
    
    return {"ok": True, "passed": passed, "total": len(samples), "results": results}


def evaluate_python_solution(qkey: str, code: str, samples: List[Tuple[str, str]], tmpdir: str):
    source_path = os.path.join(tmpdir, f"{qkey}.py")
    _write_code_to_file(code, source_path)
    
    results = []
    passed = 0
    for idx, (inp, expected) in enumerate(samples, start=1):
        try:
            rc, got_out, got_err = _run_python(source_path, inp, timeout_sec=5)
            got_norm = _normalize(got_out)
            exp_norm = _normalize(expected)
            ok = (rc == 0) and (got_norm == exp_norm)
            if ok:
                passed += 1
            results.append({
                "case": idx, "ok": ok, "exit_code": rc,
                "input": inp[:1000], "expected": expected[:1000],
                "got": got_out[:1000], "stderr": got_err[:500] if got_err else ""
            })
        except subprocess.TimeoutExpired:
            results.append({
                "case": idx, "ok": False, "timeout": True,
                "input": inp[:1000], "expected": expected[:1000],
                "got": "", "stderr": "Time Limit Exceeded"
            })
    
    return {"ok": True, "passed": passed, "total": len(samples), "results": results}


def evaluate_java_solution(qkey: str, code: str, samples: List[Tuple[str, str]], tmpdir: str):
    class_match = re.search(r'public\s+class\s+(\w+)', code)
    class_name = class_match.group(1) if class_match else "Solution"
    source_path = os.path.join(tmpdir, f"{class_name}.java")
    _write_code_to_file(code, source_path)
    
    rc, out, err = _compile_java(source_path, tmpdir)
    if rc != 0:
        return {"ok": False, "summary": "Compilation failed", "compile_error": err[:2000], "results": []}
    
    results = []
    passed = 0
    for idx, (inp, expected) in enumerate(samples, start=1):
        try:
            rc2, got_out, got_err = _run_java(tmpdir, class_name, inp, timeout_sec=5)
            got_norm = _normalize(got_out)
            exp_norm = _normalize(expected)
            ok = (rc2 == 0) and (got_norm == exp_norm)
            if ok:
                passed += 1
            results.append({
                "case": idx, "ok": ok, "exit_code": rc2,
                "input": inp[:1000], "expected": expected[:1000],
                "got": got_out[:1000], "stderr": got_err[:500] if got_err else ""
            })
        except subprocess.TimeoutExpired:
            results.append({
                "case": idx, "ok": False, "timeout": True,
                "input": inp[:1000], "expected": expected[:1000],
                "got": "", "stderr": "Time Limit Exceeded"
            })
    
    return {"ok": True, "passed": passed, "total": len(samples), "results": results}


def evaluate_solution(qkey: str, language: str, code: str) -> Dict:
    """
    Evaluate a solution - NOW SUPPORTS LEETCODE!
    """
    language = language.lower()
    if language in ["c++", "cxx", "cc"]:
        language = "cpp"
    elif language in ["py", "python3"]:
        language = "python"
    
    supported_languages = ["cpp", "python", "java"]
    if language not in supported_languages:
        return {"ok": False, "error": f"Language '{language}' not supported"}
    
    cache = _load_cache()
    last = cache.get("last_selection", {})
    
    if qkey not in last:
        return {"ok": False, "error": f"No problem found for {qkey}"}
    
    problem = last[qkey]
    platform = problem.get("platform", "codeforces")
    
    # Fetch samples based on platform
    samples = []
    if platform == "codeforces":
        url = problem["link"]
        samples = _fetch_codeforces_samples(url, use_cache=True)
    elif platform == "leetcode":
        title_slug = problem.get("titleSlug")
        if not title_slug:
            return {"ok": False, "error": "LeetCode problem missing titleSlug"}
        samples = _fetch_leetcode_samples(title_slug, use_cache=True)
        
        # LeetCode special handling
        if not samples:
            return {
                "ok": True,
                "problem": problem,
                "summary": "Code received for LeetCode problem",
                "message": (
                    f"✅ Code received for: {problem['name']}\n\n"
                    f"⚠️ LeetCode problems have limited public test cases.\n\n"
                    f"🔗 Submit on LeetCode for full validation:\n{problem['link']}\n\n"
                    f"💡 Your code has been saved."
                ),
                "platform": "leetcode",
                "leetcode_link": problem['link'],
                "note": "Submit on LeetCode.com for comprehensive testing"
            }
    else:
        return {"ok": False, "error": f"Platform '{platform}' not supported"}
    
    if not samples:
        return {
            "ok": False,
            "problem": problem,
            "summary": f"No sample tests available for {platform}",
            "error": "Samples unavailable"
        }
    
    print(f"✅ Found {len(samples)} sample tests for {platform}")
    
    tmpdir = tempfile.mkdtemp(prefix=f"eval_{qkey}_", dir=SUBMISSIONS_DIR)
    
    try:
        if language == "cpp":
            eval_result = evaluate_cpp_solution(qkey, code, samples, tmpdir)
        elif language == "python":
            eval_result = evaluate_python_solution(qkey, code, samples, tmpdir)
        elif language == "java":
            eval_result = evaluate_java_solution(qkey, code, samples, tmpdir)
        else:
            return {"ok": False, "error": f"Language {language} not implemented"}
        
        if eval_result["ok"]:
            passed = eval_result["passed"]
            total = eval_result["total"]
            score = round(100 * passed / total) if total > 0 else 0
            eval_result["summary"] = f"Passed {passed}/{total} tests · Score: {score}%"
            eval_result["score"] = score
            
            if platform == "leetcode":
                eval_result["note"] = "⚠️ Limited test cases. Submit on LeetCode for full validation."
        
        eval_result["problem"] = problem
        eval_result["language"] = language
        eval_result["platform"] = platform
        return eval_result
        
    except Exception as e:
        return {"ok": False, "error": f"Evaluation error: {str(e)}", "problem": problem}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    print("✅ Evaluator loaded - supports Codeforces and LeetCode!")