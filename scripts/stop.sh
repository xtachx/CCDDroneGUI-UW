#!/bin/bash

PIDFILE=logs/gunicorn.pid

if [ -f "$PIDFILE" ] ; then
    PID="$(cat $PIDFILE)"
    if [ -n "$PID" ] ; then
	kill $PID && rm $PIDFILE
    else
	echo "No running process" >&2
    fi
else
    echo "No PID file" >&2
    
fi

