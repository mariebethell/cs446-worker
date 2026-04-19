FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN playwright install --with-deps

COPY . .

CMD ["gunicorn", "-b", ":8080", "app:app"]