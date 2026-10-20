FROM python:3.11-slim

WORKDIR /app/backend

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

# Copy project
COPY backend/ .

# Make start script executable
COPY backend/start.sh .
RUN chmod +x start.sh

# Expose port
EXPOSE 8000

# Command to run
CMD ["gunicorn", "hydria.wsgi:application", "--bind", "0.0.0.0:8000"]
