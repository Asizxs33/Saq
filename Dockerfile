FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Данные (SQLite, кэш OpenSanctions, чёрные списки) живут в volume — см. docker-compose.yml
VOLUME ["/srv/data"]

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
