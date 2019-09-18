#!/bin/bash

# Start the CCDDroneGUI server

mydir=$(cd `dirname $0` ; pwd)
cd $(dirname "$mydir")

CFGFILE="$1"
[ -n "$CFGFILE" ] && CFGFILE="cfgfile=\"$CFGFILE\""
[ -z "$PORT" ] && PORT=5001


export GUNICORN_CMD_ARGS="--capture-output --log-file=logs/gunicorn.error \
  --reload -b 0.0.0.0:$PORT -w 1 -D --pid logs/gunicorn.pid --threads 4"

./venv/bin/gunicorn "CCDDroneGUI:create_app($CFGFILE)"

