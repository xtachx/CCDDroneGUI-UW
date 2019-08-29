#!/bin/bash

# Start the CCDDroneGUI server

mydir=$(cd `dirname $0` ; pwd)
cd $(dirname "$mydir")

CFGFILE="$1"
[ -z "$CFGFILE" ] && CFGFILE="config.default.py"
PORT=5001


export GUNICORN_CMD_ARGS="--capture-output \
  --log-file=logs/gunicorn.error \
  -b 0.0.0.0:$PORT -w 1 -D --pid logs/gunicorn.pid"

./venv/bin/gunicorn "CCDDroneGUI:create_app(cfgfile=\"$CFGFILE\")"

