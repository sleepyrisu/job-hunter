FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium --with-deps

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8888

# gunicorn.conf.py controls bind/workers/threads and starts the scheduler thread.
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
