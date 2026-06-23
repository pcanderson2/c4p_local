FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY digest.py template.html ./
CMD ["python", "-u", "digest.py"]
