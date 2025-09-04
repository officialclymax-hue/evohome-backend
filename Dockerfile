# Dockerfile (recommended)
FROM python:3.11-slim

# system deps for psycopg2, etc
RUN apt-get update && apt-get install -y build-essential libpq-dev gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# install
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

EXPOSE 8000
# Use uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
