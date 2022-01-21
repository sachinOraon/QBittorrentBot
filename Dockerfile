FROM python:3.9-slim
RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get upgrade -y && apt-get install -y gcc python3-dev
COPY . /usr/src/app
WORKDIR /usr/src/app
RUN ["pip", "install", "--no-cache-dir", "-r", "requirements.txt"]
ENTRYPOINT ["python", "-u", "main.py"]
