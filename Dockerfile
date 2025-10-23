# Dockerfile

# Start with an official Python base image
FROM python:3.11-slim

# --- ADD THIS BLOCK ---
# Install system dependencies:
# g++ for C++ compilation
# openjdk-17-jdk for Java compilation/runtime
RUN apt-get update && \
    apt-get install -y build-essential default-jdk --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*
# -------------------

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file first to leverage Docker's build cache
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# --- ADD THIS LINE ---
# Install Playwright browsers (needed if Playwright is used)
RUN playwright install --with-deps chromium
# -------------------

# Copy the rest of your application's code into the container
COPY . .

# Tell Docker what command to run when the container starts
CMD ["uvicorn", "services.api_wrapper:app", "--host", "0.0.0.0", "--port", "8000"]