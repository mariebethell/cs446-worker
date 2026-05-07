FROM mcr.microsoft.com/playwright/python:v1.43.0

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["gunicorn", "-b", ":8080", "app:app"]