from flask import (Flask, render_template, request, redirect, url_for, flash, 
                   json, make_response, abort, send_file)
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
import subprocess
import tempfile


# some utility functions
def hostname():
    return socket.gethostname()

def system():
    return hostname().split('.')[0]

# create the application
def create_app(cfgfile=None, instance_path=None):
    
    app = Flask(__name__, instance_path=instance_path,
                instance_relative_config=bool(instance_path))

    # see if a config file exists and load it
    def try_config(filename):
        """ if filename exists, load it. return true if load successful """
        # test file, allow a 'config' subdir
        if not os.path.isfile(filename):
            filename = os.path.join('config', filename)
        print("Testing for config file", filename)
        if os.path.isfile(filename):
            print("Loading configuration from", filename)
            if filename.endswith('.py'):
                app.config.from_pyfile(filename)
            elif filename.endswith('.json'):
                app.config.from_json(filename)
            else:
                print("Unknown suffix on file f{filename}, assume pyfile")
                app.config.from_pyfile(filename)
            return True
        return False


    if cfgfile:
        if not try_config(cfgfile):
            raise FileNotFoundError(cfgfile)
    else:
        testfiles = ('config.'+system()+'.py',
                     'config.'+hostname()+'.py',
                     'config.default.py')
        for fname in testfiles:
            if try_config(fname):
                break
    
    app.config.setdefault('DATAPATH','data')
    app.config.setdefault('LOGFILE','logs/CCDDroneGUI.log')
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
    #logging.getLogger('werkzeug').setLevel(logging.WARNING)
    
    # set up handlers
    BasicAuth(app)
    Bootstrap(app)
    ImageDB.ImageDB(app=app)
    # executor runs the actual programs
    app.executor = Executor(app.config)
    atexit.register(app.executor.abort)
    
    def getdb():
        return app.extensions['ImageDB']
    
    def _getcache(key):
        return getdb().getcache(key)
    
    def _setcache(key, val):
        getdb().setcache(key, val)
    
    app.add_template_global(hostname)
    app.add_template_global(system)

    @app.template_global()
    def dtype(val):
        return type(val).__name__

    @app.route('/')
    def index():
        return render_template("index.html")

    @app.route('/api/status')
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
                               droneconfig=config if config is not None else "")


    @app.route('/abort', methods=('POST', ))
    def abortproc():
        app.executor.abort()
        flash("Abort submitted", 'warning')
        return redirect(url_for('index'))

    @app.route('/endexposeloop', methods=('POST', ))
    def endexposeloop():
        app.executor.endexposureloop()
        flash("Exposures will end after current one", 'success')
        return redirect(url_for('index'))


    ####### database browser endpoints ###########
    @app.route('/show/<filename>')
    def showfile(filename):
        info = getdb().find_one({'filename': filename})
        if not info:
            abort(404, f"No registered file with name '{filename}'")
        return render_template('showfile.html',fileinfo=info)

    @app.route('/api/getimg/<filename>')
    def getimg(filename):
        datapath = app.config.get('DATAPATH')
        filepath = os.path.join(datapath, filename)
        if not os.path.isfile(filepath):
            abort(404, f"Raw fits file '{filename}' not present")
        with tempfile.NamedTemporaryFile(suffix='.png') as tmpfile:
            tmpname = tmpfile.name
            subprocess.run(['fits2bitmap', filepath, '-o', tmpname, 
                            '--percent', '98'])
            return send_file(tmpname)
        return abort(500, "something went wrong sending file...")

    @app.route('/list')
    def list():
        columns = ('EXPSTART', 'RUNTYPE', 'NOTES', 'filename')
        data = getdb().find({}, {c:True for c in columns},
                            sort=(('EXPSTART',-1),) )

        # find columns that have limited choices
        selectOptions = {}
        reqmd = getdb().getconfig().get('required_metadata',[])
        for key, comment, dtype, allowed in reqmd:
            if key in columns and allowed:
                selectOptions[key] = allowed
        return render_template("datatable.html",
                               columns=columns, data=data, 
                               selectOptions=selectOptions)
        
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
