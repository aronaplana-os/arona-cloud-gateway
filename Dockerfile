FROM python:3.12-slim
WORKDIR /app
COPY cloud_gateway.py /app/cloud_gateway.py
ENV PORT=8080
EXPOSE 8080
CMD ["python", "-u", "cloud_gateway.py"]
