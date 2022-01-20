FROM python:3.9-slim
RUN apt-get update && apt-get upgrade -y && apt-get install -y gcc python3-dev
COPY . /usr/src/app
WORKDIR /usr/src/app
RUN ["pip", "install", "-r", "requirements.txt"]
ENTRYPOINT ["python", "-u", "main.py"]
