#!/usr/bin/env python3
from ImageDB import validate_metadata
import sys
import socket
import subprocess
import shutil
import os
import json


def printusage():
    print(F"Usage: {sys.argv[0]} <fitsfile> <exposure> <cfgfile> <metafile>")
    sys.exit(1)


if len(sys.argv) < 5:
    printusage()

fitsfile, exposure, cfgfile, metafile = sys.argv[1:]
if not fitsfile.endswith('.fits'):
    fitsfile += '.fits'

fitsfile = os.path.abspath(fitsfile)
cfgfile = os.path.abspath(cfgfile)

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
print("Running CCDDExpose")
res = subprocess.run(['./CCDDExpose', fitsfile, exposure, cfgfile],
                     cwd=CCDDronePath)
if res.returncode:
    sys.exit(res.returncode)


# call updatedb
print("Running CCDDUpdateDB")
res = subprocess.run(['./CCDDUpdateDB.py', fitsfile, metafile])
if res.returncode:
    sys.exit(res.returncode)

print("Done")
sys.exit(0)
