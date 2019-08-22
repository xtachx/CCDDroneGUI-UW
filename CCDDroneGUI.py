from flask import Flask, render_template, request, redirect, url_for, flash
from flask_bootstrap import Bootstrap
import logging
from glob import glob

# create the application
def create_app(cfgfile=None, instance_path=None):
    
    app = Flask(__name__, instance_path=instance_path,
                instance_relative_config=bool(instance_path))

    # configuration if file was given
    if cfgfile:
        app.config.from_pyfile(cfgfile)
    
    app.config.setdefault('CCDDmetadata','CCDDmetadata.ini')
    app.config.setdefault('CCDDconfig','CCDDconfig.ini')
    app.config.setdefault('datapath','/data/local/fitsfiles')
        
    # set up logging
    logformat = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    if app.debug:
        logging.basicConfig(format=logformat, level=logging.DEBUG)
    else:
        logfile = app.config.get('LOGFILE')
        if logfile:
            from logging.handlers import RotatingFileHandler
            level = app.config.get('LOGLEVEL',logging.WARNING)
            logging.basicConfig(filename=logfile, format=logformat, level=level)

            file_handler = RotatingFileHandler(logfile, maxBytes=1024*1024*100,
                                               backupCount=20)
            file_handler.setLevel(app.config.get('LOGLEVEL',logging.DEBUG))
            formatter = logging.Formatter(format)
            file_handler.setFormatter(formatter)
            app.logger.addHandler(file_handler)
    
    # set up handlers
    Bootstrap(app)
    
    @app.route('/')
    def index():
        return render_template("index.html")

    @app.route('/expose', methods=('GET','POST'))
    def expose():
        if request.method == "POST":
            flash("Exposure started",'success')
            return redirect(url_for('index'))
        if request.method == 'GET':
            with open(app.config['CCDDmetadata']) as f:
                metadata = f.read()
            return render_template("expose.html", metadata=metadata)
        
    return app
    

if __name__ == '__main__':
    app = create_app()
    app.config.update({'DEBUG':True,'TESTING':True, 
                       'TEMPLATES_AUTO_RELOAD':True,
                       #'EXPLAIN_TEMPLATE_LOADING':True,
                      })
    app.templates_auto_reload = True
    app.secret_key = "not very secret is it?"
    
    app.run(host='0.0.0.0', port=5001, extra_files=glob("templates/*.html"))           
