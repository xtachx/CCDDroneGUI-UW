from flask import (Flask, render_template, request, redirect, url_for, flash, 
                   json, make_response)
from flask_bootstrap import Bootstrap
from flask_basicauth import BasicAuth
import logging
from glob import glob
import ImageDB
from forms import ExposeForm
import sys
import socket
import os
from Executor import Executor
from logging.handlers import RotatingFileHandler
import atexit

# create the application
def create_app(cfgfile='config.default.py', instance_path=None):
    
    app = Flask(__name__, instance_path=instance_path,
                instance_relative_config=bool(instance_path))

    # configuration if file was given
    if cfgfile:
        app.config.from_pyfile(cfgfile)
    
    app.config.setdefault('CCDDCONFIGFILE','config/Config_GUI.ini')
    app.config.setdefault('DATAPATH','/data/local/fitsfiles')
    app.config.setdefault('LOGFILE','logs/CCDDroneGUI.log')
    app.config.setdefault('CCDDRONEPATH', 
                          os.path.expanduser("~/software/CCDDrone"))
    app.config.setdefault('BASIC_AUTH_USERNAME', 'ccduser')
    app.config.setdefault('BASIC_AUTH_PASSWORD', 'ccduser')
    app.config.setdefault('BASIC_AUTH_FORCE', True)
    if not app.secret_key:
        app.secret_key = 'dev'
        
    # set up logging
    logformat = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    loglevel = app.config.get('LOGLEVEL', logging.WARNING)
    if app.debug:
        loglevel = logging.DEBUG
    logfile = app.config.get('LOGFILE')
    logging.basicConfig(format=logformat, level=loglevel, filename=logfile)
    if logfile:
        file_handler = RotatingFileHandler(logfile, maxBytes=1024*1024*100,
                                           backupCount=20)
        file_handler.setLevel(loglevel)
        formatter = logging.Formatter(logformat)
        file_handler.setFormatter(formatter)
        app.logger.addHandler(file_handler)
    # turn down werkzeug logs
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    
    # set up handlers
    BasicAuth(app)
    Bootstrap(app)
    ImageDB.ImageDB(app=app)
    # executor runs the actual programs
    app.executor = Executor(app.config)
    atexit.register(app.executor.abort)
    
    def _getcache(key):
        return app.extensions['ImageDB'].getcache(key)
    
    def _setcache(key, val):
        app.extensions['ImageDB'].setcache(key, val)
    
    @app.template_global()
    def hostname():
        return socket.gethostname()
    
    @app.template_global()
    def system():
        return hostname().split('.')[0]

    @app.template_global()
    def ccddpath():
        return app.config.get('CCDDRONEPATH')

    @app.template_global()
    def dtype(val):
        return type(val).__name__

    @app.route('/')
    def index():
        return render_template("index.html")

    @app.route('/status')
    def status():
        return json.jsonify(app.executor.getstatus())

    @app.errorhandler(RuntimeError)
    @app.errorhandler(FileNotFoundError)
    def runtime_error(err):
        flash(f"ERROR: {str(err)}", 'danger')
        return redirect(url_for('index'))
        
    @app.route('/expose', methods=('GET','POST'))
    def expose():
        cachekey = 'last_exposure_settings_'+system()
        # get the last values we used
        lastvals = _getcache(cachekey)
        if lastvals is None:
            lastvals = {'metadata': {}}
        lastvals['metadata']['SYSTEM'] = system()
        form = ExposeForm(request.form, data=lastvals)
        
        if request.method == "POST" and form.validate():
            _setcache(cachekey, form.data)
            app.executor.savemetadata(form.metadata.data)
            app.executor.ExposeLoop(form.nexposures.data,
                                    form.filename.data,
                                    form.exposure.data)
            flash('Exposure started', 'success')
            return redirect(url_for('index'))

        # always default to 1 exposure for new starts 
        form.nexposures.process_data(1)
        return render_template("expose.html", form=form)
        
    @app.route('/startup', methods=('POST',))
    def startup():
        app.executor.StartupAndErase()
        flash('StartupAndErase started', 'success')
        return redirect(url_for('index'))

    @app.route('/erase', methods=('POST',))
    def erase():
        app.executor.PerformEraseProcedure()
        flash('Erase procedure started', 'success')
        return redirect(url_for('index'))

    @app.route('/editconfig', methods=('GET', 'POST'))
    def editconfig():
        if request.method == 'POST':
            app.executor.saveconfig(request.form['config'],
                                    'apply' in request.form)
            flash("Configuration saved", "success")
            return redirect(url_for('index'))
        config = app.executor.readconfig()
        if config is None:
            flash(f"Unable to load config file {app.executor.outputConfig}",
                  'danger')
        return render_template("editconfig.html", 
                               config=config if config is not None else "")


    @app.route('/abort', methods=('POST', ))
    def abort():
        app.executor.abort()
        flash("Abort submitted", 'warning')
        return redirect(url_for('index'))

    @app.route('/endexposeloop', methods=('POST', ))
    def endexposeloop():
        app.executor.endexposureloop()
        flash("Exposures will end after current one", 'success')
        return redirect(url_for('index'))

    return app

    

if __name__ == '__main__':
    cfgfile = 'config.default.py'
    if len(sys.argv) > 1:
        cfgfile = sys.argv[1]
    app = create_app(cfgfile)
    app.config.update({'DEBUG':True,'TESTING':True, 
                       'TEMPLATES_AUTO_RELOAD':True,
                       #'EXPLAIN_TEMPLATE_LOADING':True,
                      })
    app.templates_auto_reload = True
    extra_files = glob("templates/*.html")
    extra_files.append(cfgfile)
    app.run(host='0.0.0.0', port=5001, extra_files=extra_files)           
