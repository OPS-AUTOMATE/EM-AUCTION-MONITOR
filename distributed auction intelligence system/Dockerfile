FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure permissions (optional but good practice)
# RUN chmod +x main.py

# Run string unbuffered to see logs immediately
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
