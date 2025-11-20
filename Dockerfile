# Base image with Python 3.11. Slim variant keeps the image size down.
FROM python:3.11-slim

# Set working directory inside the container. All subsequent commands
# will be run in this directory.
WORKDIR /app

# Copy dependency definitions first to leverage Docker layer caching. This
# means Docker will only re-install dependencies when requirements.txt
# changes.
COPY requirements.txt ./

# Install Python dependencies. The --no-cache-dir flag prevents pip from
# caching wheels, reducing the final image size.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container.
COPY . .

# Default command to run the bot. Railway will honour this when using
# the Dockerfile builder. Avoid using python -u because python-telegram-bot
# already flushes output appropriately.
CMD ["python", "main.py"]