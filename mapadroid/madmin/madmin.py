import logging
import os

from flask import Flask, render_template
from flask.logging import default_handler
from werkzeug.middleware.proxy_fix import ProxyFix

import mapadroid
from mapadroid.db.DbWrapper import DbWrapper
from mapadroid.mad_apk import AbstractAPKStorage
from mapadroid.madmin.api import APIEntry
from mapadroid.madmin.reverseproxy import ReverseProxied
from mapadroid.madmin.routes.apks import apk_manager
from mapadroid.madmin.routes.config import config
from mapadroid.madmin.routes.control import control
from mapadroid.madmin.routes.map import map
from mapadroid.madmin.routes.path import path
from mapadroid.madmin.routes.statistics import statistics
from mapadroid.madmin.routes.event import event
from mapadroid.utils import MappingManager
from mapadroid.utils.logging import InterceptHandler, get_logger, LoggerEnums
from mapadroid.websocket.WebsocketServer import WebsocketServer

logger = get_logger(LoggerEnums.madmin)
app = Flask(__name__,
            static_folder=os.path.join(mapadroid.MAD_ROOT, 'static/madmin/static'),
            template_folder=os.path.join(mapadroid.MAD_ROOT, 'static/madmin/templates'))
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config['UPLOAD_FOLDER'] = 'temp'
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024
app.secret_key = "8bc96865945be733f3973ba21d3c5949"
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers',
                         'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods',
                         'GET,PUT,POST,DELETE,OPTIONS')
    return response


@app.errorhandler(500)
def internal_error(self, exception):
    logger.opt(exception=True).critical("An unhanded exception occurred!")
    return render_template('500.html'), 500


class madmin(object):
    def __init__(self, args, db_wrapper: DbWrapper, ws_server, mapping_manager: MappingManager, data_manager,
                     deviceUpdater, jobstatus, storage_obj):

        self._db_wrapper: DbWrapper = db_wrapper
        self._args = args
        self._app = app
        self._mapping_manager: MappingManager = mapping_manager
        self._storage_obj = storage_obj
        self._device_updater = deviceUpdater
        self._ws_server: WebsocketServer = ws_server
        self._data_manager = data_manager
        self._jobstatus = jobstatus
        self._plugin_hotlink: list = []

        self.path = path(self._db_wrapper, self._args, self._app, self._mapping_manager, self._jobstatus,
                         self._data_manager, self._plugin_hotlink)
        self.map = map(self._db_wrapper, self._args, self._mapping_manager, self._app, self._data_manager)
        self.statistics = statistics(self._db_wrapper, self._args, app, self._mapping_manager, self._data_manager)
        self.control = control(self._db_wrapper, self._args, self._mapping_manager, self._ws_server, logger,
                               self._app, self._device_updater)
        self.APIEntry = APIEntry(logger, self._app, self._data_manager, self._mapping_manager, self._ws_server,
                                 self._args.config_mode, self._storage_obj)
        self.config = config(self._db_wrapper, self._args, logger, self._app, self._mapping_manager,
                             self._data_manager)
        self.apk_manager = apk_manager(self._db_wrapper, self._args, self._app, self._mapping_manager, self._jobstatus,
                                       self._storage_obj)
        self.event = event(self._db_wrapper, self._args, logger, self._app, self._mapping_manager, self._data_manager)

    @logger.catch()
    def madmin_start(self):
        try:
            # load routes
            if self._args.madmin_base_path:
                self._app.wsgi_app = ReverseProxied(self._app.wsgi_app, script_name=self._args.madmin_base_path)
            # start modules
            self.path.start_modul()
            self.map.start_modul()
            self.statistics.start_modul()
            self.config.start_modul()
            self.apk_manager.start_modul()
            self.event.start_modul()
            self.control.start_modul()
            log = logging.getLogger('werkzeug')
            handler = InterceptHandler(log_section=LoggerEnums.madmin)
            log.addHandler(handler)
            self._app.run(host=self._args.madmin_ip, port=int(self._args.madmin_port), threaded=True)
        except:
            logger.opt(exception=True).critical('Unable to load MADmin component')
        logger.info('Finished madmin')

    def add_route(self, routes):
        for route, view_func in routes:
            self._app.route(route, methods=['GET', 'POST'])(view_func)

    def get_routepath(self):
        routepath = self._app.root_path
        return routepath

    def register_plugin(self, pluginname):
        self._app.register_blueprint(pluginname)

    def add_plugin_hotlink(self, name, link, plugin, description, author, url, linkdescription, version):
        self._plugin_hotlink.append({"Plugin": plugin, "linkname": name, "linkurl": link,
                                     "description": description, "author": author, "authorurl": url,
                                     "linkdescription": linkdescription, 'version': version})
