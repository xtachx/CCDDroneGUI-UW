#!/usr/bin/env python3
from Metadata import validate_metadata
import sys
import socket
import subprocess
import shutil
import os
import json
import tempfile
import atexit
import signal
from astropy.io import fits
import time

def printusage():
    print(F"Usage: {sys.argv[0]} <exposure> <fitsfile> <metafile> [<thumb>]")
    sys.exit(1)

_child_pid = None
def killchild(sig, frame):
    print("SIGTERM received", file=sys.stdout)
    if _child_pid:
        print("killing child process", _child_pid, file=sys.stdout)
        os.kill(_child_pid, signal.SIGKILL)
    print("Exiting", file=sys.stdout, flush=True)
    sys.exit(signal.SIGTERM)

#atexit.register(killchild)
signal.signal(signal.SIGTERM, killchild)

def run_context(*args, **kwargs):
    global _child_pid

    proc = subprocess.Popen(*args, **kwargs)
    _child_pid = proc.pid
    returncode = proc.wait()
    _child_pid = None
    if returncode != 0:
        sys.exit(returncode)


if len(sys.argv) < 4:
    printusage()

exposure, fitsfile, metafile = sys.argv[1:4]
if not fitsfile.endswith('.fits'):
    fitsfile += '.fits'
thumb = sys.argv[4] if len(sys.argv) > 4 else None

fitsfile = os.path.abspath(fitsfile)

# first, validate the metadata
with open(metafile) as mf:
    metadata = json.load(mf)
    nosys = 'SYSTEM' not in metadata
    if nosys:
        metadata['SYSTEM'] = socket.gethostname().split('.')[0]
    if not validate_metadata(metadata):
        sys.exit(1)
    if nosys:
        # need to re-save
        with open(metafile, 'w') as mf2:
            json.dump(metadata, mf2)

# locate CCDDExpose
CCDDExpose = shutil.which('CCDDExpose')
if not CCDDExpose:
    # not in path, see if it's in a parallel directory
    testpath = '.:CCDDrone:../CCDDrone:../ccddrone'
    CCDDExpose = shutil.which('CCDDExpose', path=testpath)
    if not CCDDExpose:
        print("Error: can't find CCDDExpose executable", file=sys.stderr)
        print("       please add it to PATH or link here", file=sys.stderr)
        sys.exit(1)

CCDDronePath = os.path.dirname(CCDDExpose)

# call CCDDExpose
print("Running CCDDExpose", flush=True)
run_context(['./CCDDExpose', exposure, fitsfile ], cwd=CCDDronePath)
print("File saved to", fitsfile)

# call updatedb
print("Running CCDDUpdateDB", flush=True)
print("Metafile is "+metafile)
run_context(['./CCDDUpdateDB.py', fitsfile, metafile])

time.sleep(1)
# generate the thumbnail
if thumb is not None:
    print("Generating png image", flush=True)
    
    with tempfile.NamedTemporaryFile(suffix='.png') as tmpfile:
        tmpname = tmpfile.name
        run_context(['fits2bitmap', '-o', tmpname, '--percent', '98',fitsfile])
        run_context(['convert', tmpname, '-scale', '50%', thumb])


#print some statistics

data = fits.getdata(fitsfile)
print("Image info:")
print("  Shape:", data.shape)
print("  Min:  ", data.min())
print("  Max:  ", data.max())
print("  Mean: ", round(data.mean(),2))
print("  Std:  ", round(data.std(),2))
std = data.std(axis=0)
print("  Min column std: ", round(std.min(),2))
print("  Max column std: ", round(std.max(),2))
print("  Mean column std:", round(std.mean(),2))
    
print("Done")
sys.exit(0)
