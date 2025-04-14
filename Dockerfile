FROM alpine:3.20

LABEL app.nrtk.vendor="Digital Developments"
LABEL app.nrtk.version="0.1"
LABEL app.nrtk.release-date="2025-02-19"

RUN apk add --no-cache python3

WORKDIR /app

COPY ./main.py /app/main.py

ENTRYPOINT [ "python", "/app/main.py" ]