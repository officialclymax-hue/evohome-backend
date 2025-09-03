# Use official Python 3.11 slim image
FROM python:3.11-slim

# Create app directory
WORKDIR /app

# Prevent python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system deps needed to build wheels if required
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Expose the port
EXPOSE 8000

# Start the app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
