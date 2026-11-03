FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8888

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Create symlink so both `python web/server.py` and `python alphamind/web/server.py` resolve identically
RUN ln -sfn /app /app/alphamind

EXPOSE 8888

CMD ["python", "web/server.py"]
