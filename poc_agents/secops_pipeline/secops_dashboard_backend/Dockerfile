FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files
COPY . .

# Make the startup script executable
RUN chmod +x startup.sh

EXPOSE 8081

# Use the startup script that includes data initialization
CMD ["./startup.sh"]
