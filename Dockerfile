# Use the slim image as a starting point
FROM python:3.12-slim

# Set a working directory
WORKDIR /app

# Install requests (this happens during the BUILD phase)
RUN pip install --no-cache-dir requests

# Run your script
CMD ["python", "init.py"]
