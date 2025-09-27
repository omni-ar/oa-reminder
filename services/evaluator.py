import os
import re
import json
import subprocess
import tempfile
import shutil
from bs4 import BeautifulSoup
import requests
from playwright.sync_api import sync_playwright

CACHE_FILE = "./data/problems_cache.json"
SUBMISSIONS_DIR = "./submissions"
os.makedirs(SUBMISSIONS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)

def _load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}

def _normalize(s: str) -> str:
    lines = [ln.rstrip() for ln in s.strip().splitlines()]
    return "\n".join(lines).strip()

# In services/evaluator.py

def _fetch_codeforces_samples(problem_url: str):
    """
    Scrape Codeforces using a real browser (Playwright) to bypass anti-bot measures.
    """
    html_content = ""
    try:
        with sync_playwright() as p:
            # Launch a headless Chromium browser
            browser = p.chromium.launch()
            page = browser.new_page()

            # Go to the URL and wait for the page to be fully loaded
            page.goto(problem_url, wait_until="domcontentloaded", timeout=20000)

            # Get the final HTML content of the page
            html_content = page.content()

            browser.close()

    except Exception as e:
        print(f"DEBUG: Playwright scraping failed with error: {e}")
        return []

    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "lxml")
    sample_tests = soup.select("div.sample-tests") or soup.find_all("div", class_="sample-tests")
    if not sample_tests:
        return []

    pairs = []
    for block in sample_tests:
        inputs = block.select("div.input pre")
        outputs = block.select("div.output pre")
        for i, o in zip(inputs, outputs):
            def get_text(pre):
                txt = "".join(
                    str(x) if isinstance(x, str) else ("\n" if x.name == "br" else x.get_text())
                    for x in pre.contents
                )
                return txt
            in_text = get_text(i)
            out_text = get_text(o)
            pairs.append((in_text, out_text))
    return pairs

def _write_code_to_file(code: str, path: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)

def _compile_cpp(source_path: str, exe_path: str):
    cmd = ["g++", "-std=c++17", "-O2", source_path, "-o", exe_path]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
    return proc.returncode, proc.stdout, proc.stderr

def _run_exe(exe_path: str, input_data: str, timeout_sec: int = 2):
    proc = subprocess.run(
        exe_path,
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_sec
    )
    return proc.returncode, proc.stdout, proc.stderr

def evaluate_solution(qkey: str, language: str, code: str):
    """
    qkey: 'q1' or 'q2'
    language: 'cpp' (for now)
    code: C++17 source
    Returns dict with summary and detailed results.
    """
    if language.lower() not in ["cpp", "c++", "cxx", "cc"]:
        return {"ok": False, "error": "Only C++ is supported right now."}

    cache = _load_cache()
    last = cache.get("last_selection", {})
    if qkey not in last:
        return {"ok": False, "error": f"No last selection found for {qkey}. Send /question first."}

    problem = last[qkey]
    url = problem["link"]

    # 1) scrape samples
    samples = _fetch_codeforces_samples(url)

    if not samples:
        # Graceful fallback: no samples
        return {
            "ok": False,
            "problem": problem,
            "summary": "No sample tests available (Codeforces may have blocked scraping).",
            "results": [],
            "error": "Samples unavailable"
        }

    # 2) save code & compile
    tmpdir = tempfile.mkdtemp(prefix="eval_", dir=SUBMISSIONS_DIR)
    try:
        source_path = os.path.join(tmpdir, f"{qkey}.cpp")
        exe_path = os.path.join(tmpdir, f"{qkey}.exe") if os.name == "nt" else os.path.join(tmpdir, qkey)
        _write_code_to_file(code, source_path)

        rc, out, err = _compile_cpp(source_path, exe_path)
        if rc != 0:
            return {
                "ok": False,
                "problem": problem,
                "summary": "Compilation failed",
                "compile_error": err[:2000],
                "results": []
            }

        # 3) run tests
        results = []
        passed = 0
        for idx, (inp, expected) in enumerate(samples, start=1):
            try:
                rc2, got_out, got_err = _run_exe(exe_path, inp, timeout_sec=3)
                got_norm = _normalize(got_out)
                exp_norm = _normalize(expected)
                ok = (rc2 == 0) and (got_norm == exp_norm)
                if ok:
                    passed += 1
                results.append({
                    "case": idx,
                    "ok": ok,
                    "exit_code": rc2,
                    "input": inp[:5000],
                    "expected": expected[:5000],
                    "got": got_out[:5000],
                    "stderr": got_err[:2000]
                })
            except subprocess.TimeoutExpired:
                results.append({
                    "case": idx,
                    "ok": False,
                    "timeout": True,
                    "input": inp[:5000],
                    "expected": expected[:5000],
                    "got": "",
                    "stderr": "Timed out"
                })

        total = len(samples)
        score = round(100 * passed / total)
        summary = f"Passed {passed}/{total} sample tests · Score: {score}/100"

        return {
            "ok": True,
            "summary": summary,
            "problem": problem,
            "results": results
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
