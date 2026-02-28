FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir salmalm

EXPOSE 8000

VOLUME ["/root/SalmAlm"]

CMD ["salmalm", "start", "--host", "0.0.0.0", "--port", "8000"]
