FROM node:18-alpine as frontend-build

# Set working directory
WORKDIR /app

# Copy frontend package.json and install dependencies
COPY ./frontend/package.json ./
RUN npm install

# Copy frontend source code
COPY ./frontend ./

# Create basic webpack configuration if needed
RUN echo 'module.exports = { output: { publicPath: "/" } };' > webpack.config.js

# Build the frontend
RUN npm run build

# Backend stage
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY ./app/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY ./app ./

# Copy fallback static files
COPY ./app/static_fallback ./static_fallback

# Create directory for static files
RUN mkdir -p /app/static

# Copy frontend build from previous stage
COPY --from=frontend-build /app/build/ /app/static/

# Expose port
EXPOSE 8080

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
