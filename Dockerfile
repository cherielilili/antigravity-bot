FROM python:3.11-slim

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget \
        gnupg \
            libglib2.0-0 \
                libnss3 \
                    libnspr4 \
                        libatk1.0-0 \
                            libatk-bridge2.0-0 \
                                libcups2 \
                                    libdrm2 \
                                        libdbus-1-3 \
                                            libxkbcommon0 \
                                                libxcomposite1 \
                                                    libxdamage1 \
                                                        libxfixes3 \
                                                            libxrandr2 \
                                                                libgbm1 \
                                                                    libasound2 \
                                                                        libpango-1.0-0 \
                                                                            libcairo2 \
                                                                                && rm -rf /var/lib/apt/lists/*

                                                                                WORKDIR /app

                                                                                # Copy requirements and install Python dependencies
                                                                                COPY requirements.txt .
                                                                                RUN pip install --no-cache-dir -r requirements.txt

                                                                                # Install Playwright browsers
                                                                                RUN playwright install chromium
                                                                                RUN playwright install-deps chromium

                                                                                # Copy application code
                                                                                COPY . .

                                                                                # Set environment variables
                                                                                ENV PYTHONUNBUFFERED=1

                                                                                # Run the bot
                                                                                CMD ["python", "bot.py"]
