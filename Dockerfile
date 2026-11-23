# ioSuite in a container: one image that runs the apps it is told to (APPS; none named: every app).
#
#   docker build -t iosuite .                                    every app
#   docker build -t iosuite:ai --build-arg EXTRAS=all,iopix-ai . with ioPix's AI features (search, faces, text in photos)
#   docker build -t iosuite:small --build-arg EXTRAS=iostart,iocalendar,iotask .   only these apps' packages
#
# The settings a container needs come from its environment (the machine's file, as variables): IOSUITE_DB_HOST, _PORT,
# _NAME, _USER, _PASSWORD and APPS; everything else is kept in the Shared ioSuite database. /data holds what the apps
# write on their own and the copy's log. A stack is usually one container for the suite, and one more (the same image,
# APPS=iopix) when ioPix runs apart; docker-compose.yml here is such a stack.
FROM python:3.12-slim
# what the apps call beside Python: video thumbnails and metadata (ioPix), HEIC (ioPix, ioNote), database dumps
# (ioBackup, ioPix), text in scans (ioDocs, ioRecipe), the PDF font (ioThings)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libimage-exiftool-perl libjpeg-turbo-progs libheif1 libglib2.0-0 \
      mariadb-client tesseract-ocr tesseract-ocr-eng poppler-utils fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# the packages first, from pyproject.toml alone: this layer is rebuilt only when the list of packages changes
ARG EXTRAS=all
ARG CAPTIONS=0
COPY pyproject.toml ./
RUN python - "$EXTRAS" > /tmp/requirements.txt <<'PY' && pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
import sys, tomllib
proj = tomllib.load(open("pyproject.toml", "rb"))["project"]
deps = list(proj["dependencies"])
for g in [g for g in sys.argv[1].split(",") if g]:
    deps += proj["optional-dependencies"][g]
print("\n".join(dict.fromkeys(deps)))
PY
RUN if [ "$CAPTIONS" = "1" ]; then python - > /tmp/captions.txt <<'PY' && pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/captions.txt && rm /tmp/captions.txt; fi
import tomllib
print("\n".join(tomllib.load(open("pyproject.toml", "rb"))["project"]["optional-dependencies"]["iopix-captions"]))
PY
# the program: every app's package (.dockerignore leaves out what a container does not need)
COPY . .
RUN pip install --no-cache-dir --no-deps -e . \
    && useradd --uid 1000 --user-group --create-home --shell /usr/sbin/nologin iosuite \
    && mkdir -p /data && chown -R iosuite:iosuite /data /app
# the commit the image was built from, for Settings › Servers › Updates (the workflow passes it)
ARG COMMIT=unknown
RUN echo "$COMMIT" > COMMIT
VOLUME ["/data"]
ENV DATA_DIR=/data PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1 IOSUITE_DB_HOST=db IOSUITE_DB_PORT=3306 IOSUITE_DB_NAME=iosuite IOSUITE_DB_USER=iosuite
# the pages, phones and devices, MCP; ioContact's LDAP
EXPOSE 80 443 8443 8444 3890
USER iosuite
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/-/status' % (os.environ.get('PORT') or 80), timeout=4)" || exit 1
# before it serves: the tables of the Shared ioSuite database and the first admin (iosuite_shared.stack); a stack
# file adds what it wants made or stored (--db-admin, --set) before the --
CMD ["iosuite", "stack", "--", "iosuite", "serve"]
