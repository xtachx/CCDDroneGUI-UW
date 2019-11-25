import os
import sys
import subprocess
from datetime import datetime
import logging
from threading import Thread
import json
import re
from time import sleep
from ImageDB import ImageDB
from astropy.visualization.scripts.fits2bitmap import fits2bitmap
path = os.path
log = logging.getLogger(__name__)


class Executor(object):
    """ Run CCDD processes and keep track of status """

    def __init__(self, config=None, **kwargs):
        """
        Args:
          config (dict): dictionary of config settings. will be merged with 
                         any other provided kwargs. valid keys are:
            CCDDRONEPATH (str): path to top-level of CCDDrone installation
            CCDDCONFIGFILE (str): path (under CCDDrone path) to store config
            CCDDMETADATAFILE (str): path (under CCDDrone path) to store metadata
            EXECUTOR_LOGFILE (str): where to put logs from CCDD executables
            DATAPATH (str): path to save images
            LASTIMGPATH (str): path to save png of last image taken
        """
        def getkey(key, default=None): 
            return kwargs.get(key, config.get(key, default))
        self.logfilename = getkey('EXECUTOR_LOGFILE', 'logs/Executor.log')
        self.logfile = None
        self.process = None
        self.current_exposure = None
        self.max_exposures = None
        self.exposethread = None
        self.lastfile=None
        self.lastimgpath = getkey('LASTIMGPATH', 'static/lastimg.png')
        self.datapath = getkey("DATAPATH", 'data')
        self.ccddpath = getkey('CCDDRONEPATH')
        CCDDConfigFile = getkey('CCDDCONFIGFILE','config/Config_GUI.ini')
        CCDDMetaFile = getkey('CCDDMETADATAFILE', 'config/Metadata_GUI.json')
        self.imagedb_uri = getkey("IMAGEDB_URI", ImageDB.default_uri)
        self.imagedb_collection = getkey("IMAGEDB_COLLECTION", 
                                         ImageDB.default_collection)
        # make sure the datapath exists
        if not os.path.isdir(self.datapath):
            try:
                os.mkdir(self.datapath)
            except FileNotFoundError:
                raise ValueError(f"DATAPATH '{self.datapath}' does not exist"
                                 "and can't be created")

        # make sure ccdd path is real
        if not os.path.isdir(self.ccddpath):
            raise ValueError(f"CCDDRONEPATH '{self.ccddpath}' doesn't exist")
        # make sure it is on PATH
        if self.ccddpath not in os.getenv('PATH'):
            os.environ['PATH'] = os.pathsep.join([self.ccddpath, 
                                                  os.getenv('PATH')])
        self.outputConfig = path.abspath(path.join(self.ccddpath, 
                                                   CCDDConfigFile))
        self.outputMetadata = path.join(self.ccddpath, CCDDMetaFile)
        log.debug("New executor created, config=%s, meta=%s, imagedb=%s/%s",
                  self.outputConfig, self.outputMetadata, 
                  self.imagedb_uri, self.imagedb_collection)
        
    def readconfig(self):
        """ Get the current config file and return as string """
        files = [path.join(self.ccddpath, 'do_not_touch', 'LastSettings.ini'),
                 path.join(self.ccddpath, 'config', 'Config.ini'),
                 self.outputConfig]
        last = sorted(files, reverse=True,
                      key=lambda f: path.getmtime(f) if path.isfile(f) else 0)
        
        log.debug("Reading config settings from %s", last[0])
        try:
            with open(last[0]) as f:
                return f.read()
        except FileNotFoundError:
            return None

    def saveconfig(self, newconf, apply=True):
        """ Save the config settings in `newconf` to file.
        Args:
          newconf (str):  contents of ini config file as string
          apply (bool): if True, call CCDDApplyNewSettings after
        """
        with open(self.outputConfig, 'w') as f:
            f.write(newconf)
        if apply:
            self.ApplyNewSettings()

    def savemetadata(self, newmeta):
        """ Save the metadata to file
        Args:
          metadata (dict): new metadata
        """
        with open(self.outputMetadata, 'w') as f:
            json.dump(newmeta, f)

    def getstate(self):
        state = 'idle'
        if self.process:
            if self.process.poll() is None:
                state = 'running'
            elif self.process.returncode != 0:
                state = 'error'
        if self.current_exposure is not None:
            state = 'running'
        return state

    def getstatus(self):
        """ Get out current status as a dict """
        status = dict(state=self.getstate(), runningcmd=None,
                      current_exposure=self.current_exposure,
                      max_exposures=self.max_exposures,
                      statustime=str(datetime.now())[:-7],
                      lastfile=self.lastfile)
        if self.process:
            status['lastcmd'] = self.process.args[0]
            status['lastreturn'] = self.process.poll()
            if status['state'] == 'running':
                status['runningcmd'] = path.basename(self.process.args[0])
        try:
            with open(self.logfilename, newline='') as logfile:
                ts = datetime.fromtimestamp(path.getmtime(self.logfilename))
                status['cmdoutput'] = f"Last output: {str(ts)[:-7]}\n"
                status['cmdoutput'] += '#'*80+'\n'
                lines = logfile.readlines()
                if lines and lines[-1][-1] == '\r':
                    lines[-1] = lines[-1][:-1]
                for line in lines:
                    if not line.endswith('\r'):
                        status['cmdoutput'] += line
        except FileNotFoundError:
            status['cmdoutput'] = ""
        
        # info for the lastimg to update
        status['lastimg'] = self.lastimgpath
        try:
            status['lastimg_timestamp'] = path.getmtime(self.lastimgpath)
        except FileNotFoundError:
            status['lastimg_timestamp'] = 0
        return status

    def endexposureloop(self):
        """ Stop an ongoing exposure loop """
        self.max_exposures = self.current_exposure

    def abort(self, kill=False):
        """ abort a currently running process """
        log.warning("Received abort request")
        self.current_exposure = None
        if self.getstate() == 'running':
            if kill:
                self.process.kill()
            else:
                self.process.terminate()
            with open(self.logfilename, 'a') as f:
                print("!!!!!! process killed by user !!!!!!!", file=f)

    # methods to run exectuables
    def _run(self, args, cwd=None, env=None, logmode='wb'):
        """ Run the commands in `args` in a subprocess """
        args = tuple(str(arg) for arg in args)
        if self.process and self.process.poll() is None: 
            raise RuntimeError("A process is already running")
        if self.logfile:
            self.logfile.close()
        self.logfile = open(self.logfilename, logmode, buffering=0)
        if env is not None:
            env = dict(os.environ, **env, 
                       PYTHONPATH=os.pathsep.join(sys.path))
            
        self.process = subprocess.Popen(args, cwd=cwd, stdout=self.logfile,
                                        stderr=subprocess.STDOUT, env=env)

    def StartupAndErase(self):
        return self._run(['./CCDDStartupAndErase', self.outputConfig], 
                         cwd=self.ccddpath)

    def PerformEraseProcedure(self):
        return self._run(['./CCDDPerformEraseProcedure', self.outputConfig], 
                         cwd=self.ccddpath)

    def ApplyNewSettings(self, newconf=None):
        if newconf:
            self.saveconfig(newconf, apply=False)
        return self._run(['./CCDDApplyNewSettings', 
                          path.abspath(self.outputConfig)],
                         cwd=self.ccddpath)

    def Expose(self, fitsfile, seconds=5):
        """ Expose the CCD and read a new image to `fitsfile` """
        # make sure the file has good name
        if not fitsfile.endswith('.fits'):
            fitsfile += '.fits'
        tstamp = datetime.now().strftime('_%y%m%d-%H%M')
        match = re.match(r'.*(_\d\d\d\d\d\d-\d\d\d\d)\.fits', fitsfile)
        if not match:
            fitsfile = fitsfile[:-5] + tstamp + '.fits'
        elif match.group(1) != tstamp:
            fitsfile = fitsfile[:-17] + tstamp + '.fits'
            
        fitsfile = path.join(self.datapath, fitsfile)

        self.lastfile = fitsfile
        log.info("Starting new exposure, filename=%s",
                 path.basename(self.lastfile))
        args = ['./CCDDExposeDB.py', str(seconds), fitsfile, 
                self.outputMetadata]
        if self.lastimgpath:
            args.append(self.lastimgpath)
        return self._run(args, 
                         env=dict(IMAGEDB_URI=self.imagedb_uri,
                                  IMAGEDB_COLLECTION=self.imagedb_collection)
                     )

    def _do_expose_loop(self, fitsfile, seconds):
        """ private method to perform expose loop. Do not call directly! """
        log.debug(f"Starting expose loop with {self.max_exposures} exposures")
        while (self.current_exposure is not None and 
               self.current_exposure < self.max_exposures):
            self.current_exposure += 1
            self.Expose(fitsfile, seconds)
            while self.process and self.process.poll() is None:
                sleep(5)
            if not self.process or self.process.returncode != 0:
                break
            
        self.current_exposure = None
        self.max_exposures = None

    def ExposeLoop(self, nexposures, fitsfile, seconds=5):
        """ Take multiple exposures in a loop """
        if self.process and self.process.poll() is None:
            raise RuntimeError("A process is already running")
        if self.exposethread and self.exposethread.is_alive():
            raise RuntimeError("An exposure loop is already running")

        self.current_exposure = 0
        self.max_exposures = nexposures
        self.exposethread = Thread(target=self._do_expose_loop,
                                   args=(fitsfile, seconds))
        self.exposethread.start()

    def ToggleBias(self, value):
        """ Toggle the bias on or off """
        return self._run(['./CCDDToggleBias', value], 
                         cwd=self.ccddpath)
