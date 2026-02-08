# OA-Reminder: AI-Powered Interview Practice System

An automated system that delivers daily coding problems and situational interview questions via Telegram, with integrated code evaluation and AI-powered question generation.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [n8n Workflows](#n8n-workflows)
- [API Endpoints](#api-endpoints)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [License](#license)

## Overview

OA-Reminder is a two-service architecture system designed to help software engineers prepare for technical interviews through daily practice. It fetches problems from Codeforces and LeetCode, generates situational questions using AI, and evaluates code submissions in multiple programming languages.

## Features

### Core Functionality

- **Daily Problem Delivery**: Automated delivery of 2 coding problems + 1 situational question every day at 9 PM
- **Multi-Platform Support**: Fetches problems from both Codeforces and LeetCode
- **Code Evaluation**: Supports C++, Python, and Java with sandbox execution
- **AI Question Generation**: Uses Flan-T5 model for generating unique situational interview questions
- **Question Bank Fallback**: 70+ curated questions across 7 categories (system design, algorithms, debugging, etc.)
- **Telegram Integration**: All interactions via Telegram bot with clean, formatted messages

### Technical Features

- Containerized architecture with Docker
- n8n workflow automation
- Sample test case validation
- Rate limiting for API calls
- Response caching
- Detailed execution logs

## Architecture

```
┌─────────────────┐
│   Telegram Bot  │
│   (User Input)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────────┐
│   FastAPI App   │◄─────┤  n8n Workflows   │
│  (Port 8000)    │      │  (Port 5678)     │
└────────┬────────┘      └──────────────────┘
         │
         ├─► Problem Fetcher (Codeforces/LeetCode API)
         ├─► AI Generator (Flan-T5 Model)
         └─► Code Evaluator (Docker Sandbox)
```

### Workflow Flow

**Daily Question Workflow:**

1. Schedule Trigger (9 PM daily)
2. Fetch 2 mixed problems (Codeforces + LeetCode)
3. Generate situational question (AI or Question Bank)
4. Format message
5. Send to Telegram

**Evaluation Workflow:**

1. User submits code via Telegram
2. Webhook receives submission
3. Parse language and code
4. Fetch problem test cases
5. Execute code in sandbox
6. Compare outputs
7. Send results to Telegram

## Tech Stack

- **Backend**: Python 3.11, FastAPI, Uvicorn
- **Automation**: n8n (workflow orchestration)
- **AI/ML**: Transformers (Hugging Face), Flan-T5-base
- **Bot**: pyTelegramBotAPI
- **Code Execution**: Subprocess (isolated environment)
- **Web Scraping**: BeautifulSoup4, Playwright (optional)
- **Containerization**: Docker, Docker Compose
- **APIs**: Codeforces API, LeetCode GraphQL API

## Project Structure

```
oa-reminder/
├── services/
│   ├── __pycache__/
│   ├── api_wrapper.py          # Main FastAPI application + Telegram webhook handler
│   ├── evaluator.py            # Code evaluation engine (C++/Python/Java)
│   ├── problem_fetcher.py      # Codeforces & LeetCode API integration
│   └── situational_gen.py      # AI question generator + Question Bank
├── data/
│   └── problems_cache.json     # Cached problems and history
├── submissions/                # Temporary code execution directory
├── venv/                       # Python virtual environment
├── .env                        # Environment variables (not in repo)
├── .gitignore
├── config.py                   # Configuration loader
├── bot.py                      # Standalone Telegram bot (deprecated, now in api_wrapper)
├── docker-compose.yml          # Multi-container orchestration
├── Dockerfile                  # API service container definition
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## Prerequisites

### Required Software

- Docker & Docker Compose
- Git
- Python 3.11+ (for local development)
- G++ compiler (for C++ evaluation)
- Java JDK 17+ (for Java evaluation)

### Required Accounts

- Telegram Bot Token (from @BotFather)
- Telegram Chat ID (your personal chat ID)
- (Optional) Hugging Face API Token for faster model downloads

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/yourusername/oa-reminder.git
cd oa-reminder
```

### 2. Create Environment File

Create a `.env` file in the root directory:

```env
BOT_TOKEN=your_telegram_bot_token_here
CHAT_ID=your_telegram_chat_id_here
HF_API_KEY=your_huggingface_token_here_optional
```

### 3. Pre-Download AI Model (Recommended)

Before first run, download the Flan-T5 model to avoid timeout issues:

### 4. Build and Start Services

```bash
# Build containers (first time or after code changes)
docker compose build

# Start all services
docker compose up -d

# Check status
docker ps
```

You should see two containers running:

- `oa_api_service` (FastAPI on port 8000)
- `n8n_service` (n8n on port 5678)

## Configuration

### n8n Workflow Setup

1. Open n8n dashboard: `http://localhost:5678`

2. Create credentials for Telegram Bot:
   - Settings → Credentials → Add Credential
   - Type: Telegram
   - Bot Token: (from .env)

3. Import workflows (or create manually):

**Daily Question Workflow:**

- Trigger: Schedule (Every day at 9 PM)
- HTTP Request: GET `http://api:8000/mixed-problems`
- HTTP Request: GET `http://api:8000/situational`
- Code: Format message
- Telegram: Send message

**Evaluation Workflow:**

- Webhook: POST `/webhook/evaluate`
- Parse Input: Extract qkey, language, code, chat_id
- HTTP Request: POST `http://api:8000/evaluate`
- Code: Format result
- Telegram: Send result

4. Activate both workflows (toggle switch to green)

5. Increase timeouts (if needed):
   - Each HTTP Request node → Settings → Timeout: 120000 (120 seconds)

### Environment Variables in docker-compose.yml

Add these to n8n service for better performance:

```yaml
environment:
  - EXECUTIONS_TIMEOUT=600
  - EXECUTIONS_TIMEOUT_MAX=1200
```

## Usage

### Daily Automated Messages

Once configured, the system automatically sends messages at 9 PM every day. No manual intervention required.

### Manual Commands (Telegram)

**Get Problems:**

```
/question
```

Returns 2 coding problems + 1 situational question

**Submit Solution:**

```
solution q1 cpp
#include <iostream>
using namespace std;
int main() {
    // your code
    return 0;
}
```

Format: `solution <qkey> <language>`

- qkey: q1, q2, q3, q4
- language: cpp, python, java

**Get Problem Details:**

```
/details q1
```

Shows full problem description (Codeforces only)

### Testing the System

```bash
# Test API directly
curl http://localhost:8000/health
curl http://localhost:8000/mixed-problems
curl http://localhost:8000/situational

# View logs
docker logs -f oa_api_service
docker logs -f n8n_service

# Execute n8n workflow manually
# Open http://localhost:5678
# Click workflow → "Execute workflow" button
```

## n8n Workflows

### Daily Question Workflow

**Nodes:**

1. Schedule Trigger (Cron: 0 21 \* \* \*)
2. HTTP Request (Get Mixed Problems)
3. HTTP Request (Get Situational)
4. Code (Format Message)
5. Telegram (Send Message)

**Schedule Configuration:**

- Trigger Interval: Days
- Days Between Triggers: 1
- Trigger at Hour: 21 (9 PM)
- Trigger at Minute: 0

### Evaluate Solution Workflow

**Nodes:**

1. Webhook Trigger (POST)
2. Parse Input
3. HTTP Request (Evaluate)
4. Format Reply
5. Telegram (Send Result)

**Webhook URL:** `http://localhost:5678/webhook/evaluate`

## API Endpoints

### GET /health

Health check endpoint

```json
{ "ok": true }
```

### GET /mixed-problems

Fetch mixed problems from Codeforces and LeetCode

```bash
curl "http://localhost:8000/mixed-problems?count=2"
```

Response:

```json
{
  "ok": true,
  "items": [
    {
      "qkey": "q1",
      "name": "Two Arrays",
      "rating": 1400,
      "link": "https://codeforces.com/problemset/problem/1288/A",
      "platform": "codeforces"
    },
    {
      "qkey": "q2",
      "name": "Valid Sudoku",
      "difficulty": "Medium",
      "link": "https://leetcode.com/problems/valid-sudoku/",
      "platform": "leetcode"
    }
  ]
}
```

### GET /situational

Generate situational interview question

```bash
curl http://localhost:8000/situational
```

Response:

```json
{
  "ok": true,
  "question": {
    "question": "Design a distributed cache with automatic failover...",
    "category": "System Design",
    "source": "ai",
    "date": "2026-02-08"
  }
}
```

### POST /evaluate

Evaluate code submission

```bash
curl -X POST http://localhost:8000/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "qkey": "q1",
    "language": "cpp",
    "code": "#include <iostream>\nint main() { return 0; }"
  }'
```

Response:

```json
{
  "ok": true,
  "passed": 2,
  "total": 3,
  "score": 67,
  "summary": "Passed 2/3 tests · Score: 67%",
  "results": [
    { "case": 1, "ok": true, "input": "...", "expected": "...", "got": "..." },
    { "case": 2, "ok": true, "input": "...", "expected": "...", "got": "..." },
    { "case": 3, "ok": false, "input": "...", "expected": "...", "got": "..." }
  ]
}
```

## Troubleshooting

### Common Issues

**Issue: Containers not starting**

```bash
# Check logs
docker logs oa_api_service
docker logs n8n_service

# Restart
docker compose down
docker compose up -d
```

**Issue: Port already in use**

```bash
# Stop all Docker containers
docker compose down

# Kill specific port (Windows)
netstat -ano | findstr :5678
taskkill /PID <PID> /F

# Kill specific port (Linux/Mac)
lsof -ti:5678 | xargs kill -9
```

**Issue: n8n workflow timeout**

- Increase timeout in HTTP Request nodes (Settings → Timeout: 120000)
- Add environment variables to docker-compose.yml (see Configuration)

**Issue: AI model not loading**

```bash
# Pre-download model manually
docker exec -it oa_api_service bash
python -c "from transformers import T5Tokenizer, T5ForConditionalGeneration; T5Tokenizer.from_pretrained('google/flan-t5-base'); T5ForConditionalGeneration.from_pretrained('google/flan-t5-base')"
exit
docker compose restart api
```

**Issue: Scheduled workflow not running**

- Check workflow is Active (green toggle in n8n)
- Verify Schedule Trigger configuration
- Check n8n logs: `docker logs n8n_service | grep "workflow execution"`
- Check Executions tab in n8n dashboard

**Issue: Code evaluation failing**

```bash
# Verify compilers installed
docker exec -it oa_api_service g++ --version
docker exec -it oa_api_service java -version
docker exec -it oa_api_service python --version
```

### Log Files

```bash
# Real-time API logs
docker logs -f oa_api_service

# Real-time n8n logs
docker logs -f n8n_service

# Last 100 lines
docker logs --tail 100 oa_api_service

# Since specific time
docker logs --since 1h oa_api_service
```

### Reset Everything

```bash
# Stop and remove containers
docker compose down

# Remove cached data (optional)
rm -rf data/problems_cache.json

# Rebuild from scratch
docker compose build --no-cache
docker compose up -d
```

## Development

### Local Development (Without Docker)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run API server
python -m services.api_wrapper

# Run Telegram bot (deprecated)
python bot.py
```

### Running Tests

```bash
# Test problem fetcher
python -c "from services.problem_fetcher import fetch_mixed_problems; print(fetch_mixed_problems(count=2))"

# Test situational generator
python -c "from services.situational_gen import generate_situational_question; print(generate_situational_question(use_ai=False))"

# Test evaluator (requires a problem in cache)
python -c "from services.evaluator import evaluate_solution; print(evaluate_solution('q1', 'python', 'print(42)'))"
```

### Code Structure

**api_wrapper.py**: Main FastAPI application

- Handles Telegram webhook
- Exposes REST API endpoints
- Routes requests to service modules

**problem_fetcher.py**: Problem sourcing

- Codeforces API integration
- LeetCode GraphQL integration
- Response caching
- Rate limiting

**evaluator.py**: Code execution engine

- Multi-language support (C++, Python, Java)
- Sandbox execution with timeout
- Test case validation
- Result formatting

**situational_gen.py**: Question generation

- Flan-T5 AI model integration
- Question bank (70+ curated questions)
- Deduplication logic
- Category rotation

### Adding New Languages

To add support for a new language (e.g., JavaScript):

1. Add evaluation function in `evaluator.py`:

```python
def evaluate_javascript_solution(qkey, code, samples, tmpdir):
    # Implementation
    pass
```

2. Update `evaluate_solution()` to handle the new language

3. Update API schema in `api_wrapper.py`:

```python
language: str = Field(..., pattern=r"^(cpp|python|java|javascript)$")
```

4. Install runtime in Dockerfile:

```dockerfile
RUN apt-get install -y nodejs npm
```

## License

This project is licensed under the MIT License. See LICENSE file for details.

---

## Notes

- Requires stable internet connection for API calls
- First model download takes 5-10 minutes
- Codeforces API has rate limits (use caching)
- LeetCode test cases are limited (full validation requires LC submission)
- Container restart policies are set to `unless-stopped`

## Future Enhancements

- [ ] Support for more programming languages (JavaScript, Go, Rust)
- [ ] Web dashboard for statistics
- [ ] Custom problem difficulty selection
- [ ] Spaced repetition scheduling
- [ ] Company-specific question filtering
- [ ] Code quality analysis (complexity, best practices)
- [ ] Mock interview mode with timer
- [ ] Leaderboard for tracked users
