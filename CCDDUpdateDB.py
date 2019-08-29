#!/usr/bin/env python3

from ImageDB import ImageDB
from Metadata import update_file_metadata
import sys
import json
import os


def printusage():
    print(F"Usage: {sys.argv[0]} <fitsfile> [<metafile>]")
    sys.exit(1)


if len(sys.argv) < 2:
    printusage()

fitsfile = sys.argv[1]

if len(sys.argv) > 2:
    metafile = sys.argv[2]
    metadata = {}
    with open(metafile) as f:
        metadata = json.load(f)
    update_file_metadata(fitsfile, metadata, validate=False)

dburi = os.environ.get('IMAGEDB_URI', ImageDB.default_uri)
collection = os.environ.get('IMAGEDB_COLLECTION', ImageDB.default_collection)
db = ImageDB(dburi, collection)
db.insert(fitsfile, update=True)

sys.exit(0)
