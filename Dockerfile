FROM python:3.8-alpine

WORKDIR /app

ADD ./ ./

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

VOLUME /app
VOLUME /data

ENTRYPOINT ["python3", "bankdownload.py"]