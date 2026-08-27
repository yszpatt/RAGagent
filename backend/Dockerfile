FROM python:3.11-slim
WORKDIR /app
# pip install . 先装依赖（此时 app/ 尚未 COPY，wheel 为空包）；
# 运行时靠 PYTHONPATH=/app 让 uvicorn 与 rq worker 都能 import app.*。
ENV PYTHONPATH=/app
COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
