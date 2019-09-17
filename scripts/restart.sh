#!/bin/bash

PIDFILE=logs/gunicorn.pid

if [ -f "$PIDFILE" ] ; then
    PID="$(cat $PIDFILE)"
    if [ -n "$PID" ] ; then
	kill -HUP $PID
    else
	echo "No running process" >&2
	rm $PIDFILE
	$(dirname $0)/start.sh
    fi
else
    echo "No PID file" >&2
    $(dirname $0)/start.sh
fi

