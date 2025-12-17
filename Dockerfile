# Dockerfile
FROM python:3.11-slim

# set workdir
WORKDIR /app

# keep python output unbuffered (helpful for logs)
ENV PYTHONUNBUFFERED=1
ENV POETRY_VIRTUALENVS_CREATE=false

# system deps (build-essential used if you pip-install packages that need compilation)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

# copy only requirements first for better cache
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r /app/requirements.txt

# copy project files (we will override this with a bind-mount in dev)
COPY . /app

# default command (overridden by docker-compose for web & worker)
CMD ["uvicorn", "api_main:app", "--host", "0.0.0.0", "--port", "8000"]
