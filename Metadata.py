from collections import namedtuple
from astropy.io import fits
from datetime import datetime
import os

RequiredEntry = namedtuple('RequiredEntry', 
                           ['key', 'comment', 'dtype', 'allowed_values'])

default_required_metadata = (
        RequiredEntry('NOTES', 'human readable description', 'str', None),
        RequiredEntry('RUNTYPE', "data category", 'str', 
                      ('test', 'background', 'Am-241', 'Co-60', 'Ba-133', 
                       'Ar-27', 'Xe-127', 'radioxenon', 'other')),
        RequiredEntry('BIAS', 'bias voltage', 'float', None),
        RequiredEntry('TEMP', 'temperature in K', 'float', None),
        RequiredEntry('SYSTEM', 'DAQ host', 'str', None),
        RequiredEntry('DEVICE', 'CCD serial', 'str', None),
)


def validate_metadata(metadata, required=default_required_metadata):
    """Validate the metadata dict object to make sure it contains required keys
    Args:
      metadata (dict): The data to validate
      required (list): List of RequiredEntry objects specifying required keys
    """
    # validate required entries
    for key, comment, dtype, allowed_values in required:
        # make sure key is present
        if key not in metadata and key.upper() not in metadata:
            raise ValueError(f"Missing required key {key}")
        
        # make sure val is in allowed_values if provided
        val = metadata[key]
        if allowed_values is not None and val not in allowed_values:
            raise ValueError(f"{key}: Value '{val}' not in '{allowed_values}'")

    return True


def update_file_metadata(filename, metadata, validate=True):
    """Add all the metadata in the `metadata` dict to the file
    Exception will be raised on failure
    Args:
      filename (str): full path to the fitsfile to udpate
      metadata (dict): value to add/modify. fits comment fields for individual
                       keys should be in a special 'comments' key
      validate (bool): if True (default) validate the metadata before applying
    """
    if validate and not validate_metadata(metadata):
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


def get_file_metadata(filename):
    metadata = dict(fits.getheader(filename, 0))
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

    return metadata


def process_formdata(form, predata=None, required=default_required_metadata):
    """Process data returned from a web form into a metadata dict
    Args:
      form (dict): dict vals returned from an html form
      predata (dict): if provided, update this metadata
    Returns:
      metadata (dict): the processed metadata
    """
    result = predata or dict()
    comments = predata.setdefault('comments',dict())
    index = 0
    while True:
        key = form.get(f'metadata_key_{index}')
        if not key:
            break
        val = form.get(f'metadata_value_{index}')
        dtype = form.get(f'metadata_dtype_{index}', 'str')
        dtype = getattr(__builtins__,dtype)
        val = dtype(val)
        result[key] = val
        comment = form.get(f"metadata_comment_{index}")
        if comment:
            comments[key] = comment

    if not validate_metadata(result, required):
        raise ValueError("Metadata failed validation checks")

    return result
