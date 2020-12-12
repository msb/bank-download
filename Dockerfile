FROM python:3.9-slim

WORKDIR /app

ADD ./ ./

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

VOLUME /app
VOLUME /config
VOLUME /data

ENTRYPOINT ["python", "bankdownload.py"]