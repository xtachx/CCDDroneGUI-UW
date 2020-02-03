# README for CCDDroneGUI

## Installation
CCDDroneGUI is a python flask webserver that wraps the command-line CCDDrone executables. Obviously they are required.  The server also relies on a mongodb database, and the python library interface pymongo.  On a RHEL7 system, mongo can be installed via

```
yum install mongodb-server
systemctl start mongod
systemctl enable mongod
```
The last two commands will start the server and ensure it comes back up on reboot. 

The recommended way to install the necessary python packages is to use a virtual environment. If you have python3 installed, you should be able to simply run `scripts/install.sh` from this directory. 

## Configuration
On start, the server requires a config file. There is an example with explanatory comments in `config/config.default.py`. If you use the default `install.sh` script, most of these settings will not need to be changed. Some critical options are:

  - `DATAPATH`: path on disk for output fits files.  Good idea to make it an absolute path
  - `CCDDRONEPATH`: location of the CCDDrone top-level directory.  If left at the default `DummyDrone`, the server can be tested with scripts that mimic CCDDrone output. 
  - `BASIC_AUTH`: If necessary to password-protect the site, set `BASIC_AUTH_USERNAME`, `BASIC_AUTH_PASSWORD`, and set `BASIC_AUTH_FORCE=True`. 
  - `IMAGEDB`: these parameters specify the mongodb database parameters. If you have installed mongdb on localhost with default settings, you should not need to change these. OTherwise, if you have authentication required, different ports or hosts, etc., that information can be specified in `IMAGEDB_URI`.  There is generally no reason to change the collection name unless running multiple GUIs. 

## Running
Simply call 
`./scripts/start.sh <configfile>`
If a different port than the default 5001 is required, do:
`PORT=<port> ./scripts/start.sh <configfile>`

If a config file is not specified explicitly, the following files will be tried in order of preference: 

  - config.<system>.py
  - config.<hostname>.py
  - config.default.py

where <hostname> is the FQDN (e.g. foo.example.com) and <system> is the first part (e.g. foo).  

The server should now be running on the specified port.  Check the `LOGFILE` and `EXECUTOR_LOGFILE` for issues. 