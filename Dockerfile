# Dockerfile

# Start with an official Python base image
FROM python:3.11-slim

# --- ADD THIS LINE ---
# Install g++ compiler for the C++ evaluator service
RUN apt-get update && apt-get install -y g++
# -------------------

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file first to leverage Docker's build cache
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application's code into the container
COPY . .

# Tell Docker what command to run when the container starts
CMD ["uvicorn", "services.api_wrapper:app", "--host", "0.0.0.0", "--port", "8000"]