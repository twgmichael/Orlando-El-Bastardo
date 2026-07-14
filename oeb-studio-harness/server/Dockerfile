FROM python:3.12-slim

WORKDIR /app

RUN addgroup --system harness && adduser --system --ingroup harness harness

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chown -R harness:harness /app
USER harness

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
