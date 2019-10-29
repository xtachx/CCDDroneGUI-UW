import pymongo
from datetime import datetime
from Metadata import (validate_metadata, update_file_metadata, 
                      default_required_metadata, get_file_metadata)
import os
import logging
log = logging.getLogger(__name__)

def _tokey(key):
    if isinstance(key, str):
        return {'_id': key}
    return key

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
        self._config = {'required_metadata': default_required_metadata}
        if uri:
            self.connect(uri, collection, db)
        elif app:
            self.init_app(app)

    default_uri = "mongodb://localhost/ccddrone"
    default_db = 'test'
    default_collection = 'ccdimages'

    def init_app(self, app):
        """Get/set configuration from flask app"""
        uri = app.config.setdefault('IMAGEDB_URI', self.default_uri)
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

    def getconfig(self):
        dbconfig = self.collection.config.find_one({'_id': __name__})
        if dbconfig:
            self._config = dbconfig
        return self._config

    def setconfig(self, newconfig):
        if 'required_metadata' not in newconfig:
            raise KeyError("Missing 'required_metadata' key")
        self.collection.config.replace_one({'_id':__name__}, newconfig,
                                           upsert=True)
        self._config = newconfig
        return self._config
        
    def getcache(self, key):
        """Get a cached value"""
        return self.collection.cache.find_one(_tokey(key))

    def setcache(self, key, val):
        """Set a cached value"""
        self.collection.cache.replace_one(_tokey(key), val, upsert=True)
        
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
        metadata = get_file_metadata(filename)
        if not validate_metadata(metadata):
            raise ValueError(F"Invalid metadata on {filename}")

        if not update:
            return self.collection.insert_one(metadata).inserted_id
        else:
            search = dict(filename=metadata['filename'])
            self.collection.replace_one(search, metadata, upsert=True)
            return self.collection.find_one(search, {'_id': True})['_id']

    def find(self, *args, **kwargs):
        """ Run find command against the image collection. Args are passed
        directly to `pymongo.Collection.find`.
        """
        return self.collection.find(*args, **kwargs)
        
    def find_one(self, *args, **kwargs):
        """ Run `pymongo.Collection.find_one` with the args provided """
        return self.collection.find_one(*args, **kwargs)

    def count(self, filter=None):
        """ Count number of entries passing filter, or all documents """
        if not filter:
            return self.collection.estimated_document_count()
        else:
            return self.collection.count_documents(filter)
