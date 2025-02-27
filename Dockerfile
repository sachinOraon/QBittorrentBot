FROM python:3.9-slim
RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y --no-install-recommends gcc python3-dev curl procps
COPY ./requirements.txt /usr/src/app/requirements.txt
WORKDIR /usr/src/app
RUN ["pip", "install", "--no-cache-dir", "-r", "requirements.txt"]
ENTRYPOINT ["python", "-u", "main.py"]
