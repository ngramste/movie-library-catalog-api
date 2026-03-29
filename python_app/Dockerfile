FROM python:3.12-slim

ENV TZ=${TIMEZONE}

RUN apt-get update && apt-get install -y \
    ffmpeg \
    mkvtoolnix \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "app.py"]