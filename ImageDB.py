import pymongo
from astropy.io import fits
from datetime import datetime
from collections import OrderedDict
import os
import logging
log = logging.getLogger(__name__)


def metadata_allowed_values():
    """Get the allowed values for each key in runtypes"""
    return {'RUNTYPE': ('background', 'source', 'gasinjection', 'test'),
            'SOURCE': ('Am-241', 'Co-60', 'Ba-133', 'Ar-27', 'Xe-127',
                       'radioxenon'),
           }


def metadata_required_keys():
    """Get keys required for metadata"""
    return ('MEMO', 'BIAS', 'RUNTYPE', 'SYSTEM')


def validate_metadata(metadata):
    """Validate the metadata dict object to make sure it contains required keys
    """
    # make sure all required keys are present
    required_keys = metadata_required_keys()
    for key in required_keys:
        if key not in metadata and key.lower() not in metadata:
            print(f"Error, missing required key {key}")
            return False

    # make sure keys with restricted choices are correct
    for key, values in metadata_allowed_values().items():
        if key in metadata and metadata[key] not in values:
            print(f"Error, allowed values for {key} are {values}")
            return False

    # if runtype is 'gasinjection' or 'source', key 'source' must be set
    if (metadata['RUNTYPE'] in ('source', 'gasinjection') and
        'SOURCE' not in metadata):
        print("Error: 'source' must be specified for this runtype")
        return False

    return True


def update_metadata(filename, metadata, validate=True):
    """Add all the metadata in the `metadata` dict to the file
    Exception will be raised on failure
    Args:
      filename (str): full path to the fitsfile to udpate
      metadata (dict): value to add/modify. fits comment fields for individual
                       keys should be in a special 'comments' key
      validate (bool): if True (default) validate the metadata before applying
    """
    if not validate_metadata(metadata):
        raise ValueError("Invalid metadata")

    with fits.open(filename, 'update') as hdulist:
        header = hdulist[0].header
        header.add_history(f"Metadata modified on {datetime.utcnow()}")
        comments = metadata.pop('comments', {})
        header.update(metadata)
        for key, value in comments.items():
            header.comments[key] = value

        # just in case someone wants to keep metadata around...
        metadata['comments'] = comments


class ImageDB(object):
    def __init__(self, uri=None, collection=None, db=None, app=None):
        """Open a connection to the database
        Args:
            uri (str): a mongodb uri for which server to connect to
            collection (str): the name of the collection holding image info
            db (str): name of the db to connect to. not needed if part of uri
            app (Flask): a flask application, if present, call init_app
        """
        self.client = None
        self.db = None
        self.collection = None
        if uri:
            self.connect(uri, collection, db)
        elif app:
            self.init_app(app)

    default_uri = "mongodb://ccd21.pnl.gov/silas"
    default_db = 'test'
    default_collection = 'ccdimages'

    def init_app(self, app):
        """Get/set configuration from flask app"""
        uri = app.config.setdefaut('IMAGEDB_URI', self.default_uri)
        collection = app.config.setdefault('IMAGEDB_COLLECTION',
                                           self.default_collection)
        self.connect(uri, collection)
        app.extensions['ImageDB'] = self

    def connect(self, uri, collection=None, db=None):
        """(re)-connect to the database. parameters are as the constructor"""
        log.info("Connecting to database at %s", uri)
        self.client = pymongo.MongoClient(uri)
        if db is None:
            try:
                self.database = self.client.get_default_database()
            except pymongo.errors.ConfigurationError:
                log.warning("Database info not provided, connecting to %s",
                            self.default_db)
                db = self.default_db
        self.db = self.client.get_database(db)
        if collection is None:
            collection = self.default_collection
        self.collection = self.database.get_collection(collection)

        # we're connected, now add some indexes
        self.collection.create_index('filename', unique=True)
        self.collection.create_index('EXPSTART')
        self.collection.create_index('RUNTYPE')
        self.collection.create_index('SOURCE')

    def insert(self, filename, update=False, validate=True):
        """Insert entry for file into the database
        Args:
          filename (str): full path to fits file
          update (bool): if False (default), raise an error if an entry already
                         exists. If True, update an existing entry if present
          validate (bool): if True (default), validate the metadata taken
                           from the file before db insertion.
        Returns:
          _id: (ObjectID): the ID of the inserted or modified entry

        Raises:
          ValueError if metadata is invalid
          DuplicateKeyError if entry exists and update is False
        """
        metadata = OrderedDict(fits.getheader(filename, 0))
        if not validate_metadata(metadata):
            raise ValueError(F"Invalid metadata on {filename}")

        metadata['filepath'] = os.path.abspath(filename)
        metadata['filename'] = os.path.basename(filename)
        # format timestamp keys
        for key in ('EXPSTART', 'EXPSTOP', 'RDSTART', 'RDEND'):
            if key not in metadata:
                continue
            val = metadata[key]
            if isinstance(val, (int, float)):
                metadata[key] = datetime.fromtimestamp(val)
            elif isinstance(val, str):
                try:
                    dt = datetime.strptime(val, '%a %b %d %H:%M:%S %Y')
                    metadata[key] = dt
                except ValueError:
                    pass

        # deal with special fits card list keys
        for key in ('HISTORY', 'COMMENT'):
            if key in metadata and type(metadata[key]) is not str:
                metadata[key] = list(metadata[key])

        if not update:
            return self.collection.insert_one(metadata).inserted_id
        else:
            search = dict(filename=metadata['filename'])
            self.collection.replace_one(search, metadata, upsert=True)
            return self.collection.find_one(search, {'_id': True})['_id']
