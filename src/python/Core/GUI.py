#!/usr/bin/env python

# *IMPORTANT NOTE ON THREADS AND LOCKING*: Python currently supports
# multi-threading, but the interpreter is not multi-threaded.  The
# interpreter has a global lock, which it yields on "slow" operations
# such as file and socket operations.  On "straight" python code the
# interpreter yields the lock only every N byte code instructions;
# this server configures a large N (1'000'000).

from importlib import import_module
from imp import get_suffixes
from copy import deepcopy
from cgi import escape
from socket import gethostname
from threading import Thread, Lock
from cherrypy import expose, HTTPError, request, response, engine, log, tools, Tool
from cherrypy.lib.static import serve_file
from Cheetah.Template import Template
from Monitoring.Core.Utils import _logerr, _logwarn, _loginfo, ParameterManager
from cStringIO import StringIO
from stat import *
from jsmin import jsmin
import cPickle as pickle
import sys, os, os.path, re, tempfile, time, inspect, logging, traceback, hashlib
import json, cjson, httplib, base64

_SESSION_REDIRECT = ("<html><head><script>location.replace('%s')</script></head>"
                     + "<body><noscript>Please enable JavaScript to use this"
                     + " service</noscript></body></html>")

def extension(modules, what, *args):
  for m in modules:
    ctor = getattr(m, what, None)
    if ctor:
      return ctor(*args)
  _logwarn("extension '%s' not found" % what)
  return None

# -------------------------------------------------------------------
class SessionThread(Thread):
  """Background thread for managing the server's sessions.

   Saving each session in the HTTP service threads reduces server
   responsiveness.  For a session modified at a high burst rate in
   asynchronous requests it would be pointless to save every
   modifiation to disk.

   The server runs this separate thread to save modified sessions back
   to disk in python's pickled format.  It is essential the per-session
   data is of limited size as pickling is slow.  The output is done in
   as safe a manner as possible to avoid data loss if the server
   crashes or is restarted, and even if it is terminated forcefully
   with SIGKILL.  Modified sessions are written out about once a
   second.

   .. attribute:: _stopme

      Set by main server thread to indicate it's time to exit.

   .. attribute:: _path

      The directory where the sessions are stored.

   .. attribute:: _save

      A dictionary of sessions that must be saved."""
  def __init__(self, path):
    Thread.__init__(self, name="GUI session thread")
    self._lock = Lock()
    self._stopme = False
    self._path = path
    self._save = {}

  def save(self, data):
    """Record a session for saving.  The session's data in VALUE will
    become the property of this thread exclusively."""
    self._lock.acquire()
    self._save[data['core.name']] = data
    self._lock.release()

  def stop(self):
    """Tell the thread to stop after it has flushed all the data to disk."""
    self._lock.acquire()
    self._stopme = True
    self._lock.release()

  def run(self):
    """The thread run loop.  Checks for dirty sessions about once a
    second, and if there are any, grabs the list of currently dirty
    sessions and starts writing them to disk in pickled format.
    Manipulates session files as safely as possible."""
    while True:
      self._lock.acquire()
      stopme = self._stopme
      save = self._save
      self._save = {}
      self._lock.release()
      for (name, data) in save.iteritems():
        path = self._path + '/' + name
        tmppath = path + ".tmp"
        f = file(tmppath, "w")
        pickle.dump(data, f)
        f.close()

        try:
          os.remove(path)
        except os.error:
          pass

        try:
          os.rename(tmppath, path)
        except os.error:
          self._lock.acquire()
          self._save[name] = data
          self._lock.release()

      if stopme:
	break
      time.sleep(1)

# -------------------------------------------------------------------
tools.params = ParameterManager()
class Server:

  """The main server process, a CherryPy actor mounted to the URL tree.
  The basic server core orchestrates basic services such as session
  management, templates, static content and switching workspaces.
  Behaviour beyond these basic functions is delegated to workspaces;
  all other invocations are delegated to the current workspace of the
  session in question.

  Note that all volatile user data is stored in session objects.  The
  backends and worspaces cache data to store global state that is not
  pertinent to any particular user/browser session, allowing them to
  respond HTTP requests as quickly as possible (ideally using only
  data currently in memory).

  Configuration data:

  .. attribute:: title

     Web page banner title.

  .. attribute:: baseUrl

     URL root for this service.

  .. attribute:: serviceName

     Label for this service, to show on the web page.

  .. attribute:: services

     List of (label, url) for all monitoring services.

  .. attribute:: workspaces

     List of workspaces configured for this service.

  .. attribute:: sources

     List of data sources attached to this service.

  .. attribute:: sessiondir

     Directory where session data is kept.

  .. attribute:: logdir

     Directory where logs are sent.

  Dynamic or automatically determined configuration data:

  .. attribute:: contentpath

     Directory where static content will be found.

  .. attribute:: templates

     Cheetah template files in .contentpath.

  .. attribute:: sessions

     Currently active sessions.

  .. attribute:: sessionthread

     Background thread for saving sessions.

  .. attribute:: lock

     Lock for modifying variable data.

  .. attribute:: stamp

     Server start time for forcing session reloads.

  .. attribute:: checksums

     Server integrity check of source files."""
  def __init__(self, cfgfile, cfg, modules):
    modules = map(import_module, modules)
    self.instrument = cfg.instrument
    self.checksums = []
    self.stamp = time.time()
    self.lock = Lock()
    self.services = cfg.services
    self.serviceName = cfg.serviceName
    self.templates = {}
    self.css = []
    self.js = []

    monitor_root = os.getenv("MONITOR_ROOT")
    if os.access("%s/xdata/templates/index.tmpl" % monitor_root, os.R_OK):
      self.contentpath = "%s/xdata" % monitor_root
    else:
      self.contentpath = "%s/data" % monitor_root

    self.baseUrl = cfg.baseUrl
    self.sessiondir = cfg.serverDir + '/sessions'
    self.logdir = cfg.logFile.rsplit('/', 1)[0]
    self.title = cfg.title
    for file in os.listdir(self.contentpath + "/templates"):
      m = re.match(r'(.*)\.tmpl$', file)
      if m:
        (base,) = m.groups()
        filename = "%s/templates/%s" % (self.contentpath, file)
        self.templates[base] = [ filename, os.stat(filename)[ST_MTIME], open(filename).read() ]

    self._yui   = os.getenv("YUI_ROOT") + "/build"
    self._extjs = os.getenv("EXTJS_ROOT")
    self._d3    = os.getenv("D3_ROOT")
    self._jsroot = os.getenv("ROOTJS_ROOT")
    self._addCSSFragment("%s/css/Core/style.css" % self.contentpath)
    self._addJSFragment("%s/yahoo/yahoo.js" % self._yui)
    self._addJSFragment("%s/event/event.js" % self._yui)
    self._addJSFragment("%s/connection/connection.js" % self._yui)
    self._addJSFragment("%s/dom/dom.js" % self._yui)
    self._addJSFragment("%s/javascript/Core/sprintf.js" % self.contentpath)
    self._addJSFragment("%s/javascript/Core/Utils.js" % self.contentpath)
    self._addJSFragment("%s/javascript/Core/Core.js" % self.contentpath)

    self.sessions = {}
    self.sessionthread = SessionThread(self.sessiondir)
    self.extensions = [extension(modules, e[0], self, *e[1])
                       for e in cfg.extensions]
    self.sources = [extension(modules, s[0] + "Source", self,
                              cfg.serverDir + '/' + s[1], *s[2])
                    for s in cfg.sources]
    self.workspaces = [extension(modules, w[0] + "Workspace", self, *w[1])
                       for w in cfg.workspaces]

    for w in self.workspaces:
      if getattr(w, 'customise', None):
        w.customise()

    self._addJSFragment("%s/javascript/Core/End.js" % self.contentpath)
    self._addChecksum(None, cfgfile, open(cfgfile).read())
    for name, m in sys.modules.iteritems():
      if ((name.startswith("Monitoring.")
           and name.count(".") % 2 == 0
           and name.rsplit(".", 1)[-1][0].isupper())
          or name == "__main__") \
	 and m and m.__dict__.has_key('__file__'):
        processed = False
        # Check if the module is a binary module, since this needs a
        # special handling in python 2.7 (due to buggy handling of
        # binary modules and the inspect module )
        for suffix, mode, kind in get_suffixes():
          source = inspect.getabsfile(m)
          if 'b' in mode and source.lower()[-len(suffix):] == suffix:
            if os.path.exists(source) and os.stat(source):
              data = open(source, 'rb').read()
              self._addChecksum(name, source, data)
              processed = True
              break
        if not processed:
            self._addChecksum(name,
                              inspect.getsourcefile(m) \
                              or inspect.getabsfile(m)
                              or name,
                              inspect.getsource(m))

    self.sessionthread.start()
    engine.subscribe('stop', self.sessionthread.stop)

  def _addChecksum(self, modulename, file, data):
    """Add info for a file into the internal checksum table."""
    s = (os.path.exists(file) and os.stat(file)) or None
    self.checksums.append({
      'module': modulename,
      'srcfile': file,
      'srcname': file.rsplit("/", 1)[-1],
      'mtime': (s and s[ST_MTIME]) or -1,
      'srclen': (s and s[ST_SIZE]) or -1,
      'srcmd5': hashlib.md5(data).digest().encode('hex')
    })

  def _maybeRefreshFile(self, dict, name):
    """Possibly reload a configuration/data file."""
    self.lock.acquire()
    fileinfo = dict[name]
    mtime = os.stat(fileinfo[0])[ST_MTIME]
    if mtime != fileinfo[1]:
      fileinfo[1] = mtime
      fileinfo[2] = open(fileinfo[0]).read()
    self.lock.release()
    return fileinfo[2]
  def _templatePage(self, name, variables):
    """Generate HTML page from cheetah template and variables."""
    template = self._maybeRefreshFile(self.templates, name)
    params = { 'CSS':        "".join(x[1] for x in self.css),
               'JAVASCRIPT': "".join(x[1] for x in self.js) }
    return str(Template(template, searchList=[variables, params]))

  def _noResponseCaching(self):
    """Tell the browser not to cache this response."""
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = 'Sun, 19 Nov 1978 05:00:00 GMT'
    response.headers['Cache-Control'] = \
      'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'

  def _addCSSFragment(self, filename):
    """Add a piece of CSS to the master HTML page."""
    if not dict(self.css).has_key(filename):
      text = file(filename).read()
      if filename.startswith(self._yui):
        path = filename[len(self._yui)+1:].rsplit('/', 1)[0]
        text = re.sub(r"url\((\.\./)+([-a-z._/]+)\)", r"url(%s/yui/\2)" % self.baseUrl,
                 re.sub(r"url\(([-a-z._]+)\)", r"url(%s/yui/%s/\1)" % (self.baseUrl, path),
                   text))
      if self._extjs and filename.startswith(self._extjs):
        path = filename[len(self._extjs)+1:].rsplit('/', 1)[0]
        text = re.sub(r"url\((\.\./)+([-a-z._/]+)\)", r"url(%s/extjs/resources/\2)" % self.baseUrl,
                 re.sub(r"url\(([-a-z._]+)\)", r"url(%s/extjs/resources/%s/\1)" % (self.baseUrl, path),
                   text))
      clean = re.sub(r'\n+', '\n',
                re.sub(re.compile(r'\s+$', re.M), '',
                  re.sub(re.compile(r'^[ \t]+', re.M), ' ',
                    re.sub(r'[ \t]+', ' ',
                      re.sub(r'/\*(?:.|[\r\n])*?\*/', '', text)))))
      self.css += [(filename, "\n" + clean + "\n")]

  def _addJSFragment(self, filename, minimise=True):
    """Add a piece of javascript to the master HTML page."""
    if not dict(self.js).has_key(filename):
      text = file(filename).read()
      if minimise:
        text = jsmin(text)
      self.js += [(filename, "\n" + text + "\n")]

  # -----------------------------------------------------------------
  # Session methods.
  def _sessionClientData(self):
    for id in ('CMS-AUTH-CERT', 'CMS-AUTH-HOST'):
      if id in request.headers:
	return "%s:%s" % (id, request.headers[id])
    return request.remote.ip

  def _getSession(self, name):
    """Check NAME is valid and a known session.  If yes, returns the
    session data, otherwise None.  Locks the session before returning
    it, making sure all other threads have released the session.  The
    caller _MUST_ release the session lock before the HTTP request
    handling returns, or the next access to the session will hang."""
    s = None
    if re.match("^[-A-Za-z0-9_]+$", name):
      self.lock.acquire()
      if name not in self.sessions:
	path = "%s/%s" % (self.sessiondir, name)
        if os.path.exists(path):
	  try:
            self.sessions[name] = pickle.load(file(path, "r"))
	  except Exception, e:
	    _logerr("FAILURE: cannot load session data: " + str(e))

      s = self.sessions.get(name, None)
      self.lock.release()

      if s:
        current = self._sessionClientData()
        if s['core.clientid'] == current and s['core.name'] == name:
          if 'core.lock' not in s:
            s['core.lock'] = Lock()
          s['core.lock'].acquire()
	  s['core.stamp'] = time.time()
	else:
	  s = None
    return s

  def _saveSession(self, session):
    """Save the SESSION state."""
    self.lock.acquire()
    session['core.stamp'] = time.time()
    self.sessions[session['core.name']] = session
    self.lock.release()
    self.sessionthread.save(dict((k, deepcopy(session[k]))
                                 for k in session.keys()
                                 if k != 'core.lock'))

  def _releaseSession(self, session):
    """Release the SESSION for use by other threads."""
    session['core.lock'].release()

  def _newSession(self, workspace):
    """Create and initialise a new session with some default workspace.
    This just initialises a session; it will not become locked."""
    # Before creating a new one, purge from memory sessions that have
    # not been used for 15 minutes, to avoid building up memory use.
    self.lock.acquire()
    old = time.time() - 900
    for key in [k for k, s in self.sessions.iteritems()
		if s['core.stamp'] < old]:
      del self.sessions[key]
    self.lock.release()

    # Generate a new session key.
    (fd, path) = tempfile.mkstemp("", "", self.sessiondir)
    sessionid = (path.split('/'))[-1]
    os.close(fd)

    # Build session data.  We record:
    #  - client data for later verification
    #  - which workspace we are in
    session = {}
    session['core.name'] = sessionid
    session['core.clientid'] = self._sessionClientData()
    session['core.public'] = False
    session['core.workspace'] = self.workspaces[0].name

    user = session['core.clientid']
    if user.startswith("CMS-AUTH-CERT"):
      user = [x for x in re.findall(r"/CN=([^/]+)", user)]
      neat = [x for x in user if x.find(" ") >= 0]
      if len(neat):
	session['core.user'] = neat[0]
      else:
	session['core.user'] = user[0]
    elif user.startswith("CMS-AUTH-HOST"):
      session['core.user'] = "Console %s" % user.split(" ")[-1]
    else:
      session['core.user'] = "Host %s" % user

    # Get default objects in the workspace.
    workspace = workspace.lower()
    for w in self.workspaces:
      if w.name.lower() == workspace:
        session['core.workspace'] = w.name
      w.initialiseSession(session)

    # Get defaults also from the sources.
    for s in self.sources:
      if getattr(s, 'prepareSession', None):
        s.prepareSession(session)

    # Save the pickled session state file.
    self._saveSession(session)

    # Return the final component of the session path.
    return sessionid

  def _invalidURL(self):
    """Tell the client browser the URL is invalid."""
    return self._templatePage("invalid", {
	'TITLE'		 : re.sub(r"\&\#821[12];", "-", self.title),
	'HEADING'	 : self.title,
	'URL'		 : escape(request.request_line.split(' ')[1]),
	'ROOTPATH'	 : self.baseUrl,
	'NEWSESSION'	 : self.baseUrl,
	'HOSTNAME'	 : gethostname(),
      })

  def _workspace(self, name):
    """Get the workspace object corresponding to NAME.  If no such
    workspace exists, returns the first (= default) workspace."""
    name = name.lower()
    for w in self.workspaces:
      if w.name.lower() == name:
	return w
    return self.workspaces[0]

  # -----------------------------------------------------------------
  # Server access points.

  @expose
  @tools.params()
  def index(self):
    """Main root index address: the landing address.  Create a new
    session and redirect the client there."""
    return self.start(workspace = self.workspaces[0].name);

  @expose
  @tools.params()
  def static(self, *args, **kwargs):
    """Access our own static content."""
    if len(args) != 1 or not re.match(r"^[-a-z_]+\.(png|gif|svg)$", args[0]):
      return self._invalidURL()
    return serve_file(self.contentpath + '/images/' + args[0])

  @expose
  @tools.params()
  def yui(self, *args, **kwargs):
    """Access YUI static content."""
    path = "/".join(args)
    if not re.match(r"^[-a-z_/]+\.(png|gif|js|css)$", path):
      return self._invalidURL()
    return serve_file(self._yui + '/' + path)

  @expose
  @tools.params()
  def extjs(self, *args, **kwargs):
    """Access ExtJS static content."""
    path = "/".join(args)
    if not (self._extjs and re.match(r"^[-a-z_/]+\.(png|gif|js|css)$", path)):
      return self._invalidURL()
    return serve_file(self._extjs + '/' + path)

  @expose
  @tools.params()
  def jsroot(self, *args, **kwargs):
    """Access JSROOT static content."""
    path = "/".join(args)
    if not (self._jsroot):
      return self._invalidURL()
    return serve_file(self._jsroot + '/' + path)

  @expose
  @tools.params()
  def d3(self, *args, **kwargs):
    """Access D3 static content."""
    path = "/".join(args)
    if not (self._d3 and re.match(r"^[-a-z_/0-9\.]+\.(png|gif|js|css)$", path)):
      return self._invalidURL()
    return serve_file(self._d3 + '/' + path)

  # -----------------------------------------------------------------
  @expose
  @tools.params()
  def start(self, *args, **kwargs):
    """Jump to some content.  This creates and configures a new session with
    the desired content, as if a sequence of actions was carried out.

    In the end, redirects the client browser to a new session URL.  We
    send a HTML page with JavaScript to change the page "location",
    rather than raise a HTTPRedirect.  The main reason is HTTPRedirect
    results in HTTP 303 response and web browsers remember the
    original address not the new one we send to them.  If the user
    would then reload the page, they would not be sent back to their
    session but back to the root address which would create them again
    another session.  The second and minor reason is that we can
    verify that JavaScript is enabled in the client browser."""
    if len(args) != 0:
      return self._invalidURL()
    workspace = self._workspace(kwargs.get("workspace", self.workspaces[0].name))
    sessionid = self._newSession(workspace.name)
    session = self._getSession(sessionid)
    workspace.start(session, **kwargs)
    self._saveSession(session)
    self._releaseSession(session)
    return _SESSION_REDIRECT % (self.baseUrl + "/session/" + sessionid)

  @expose
  @tools.params()
  def workspace(self, *args, **kwargs):
    """Backward compatible version of 'start' which understands one
    parameter, the name of the workspace to begin in.  Note that
    within a session the sessionWorkspace method is used to switch
    between workspaces."""
    if len(args) == 1:
      return self.start(workspace = self._workspace(args[0]).name)
    else:
      return self.start(workspace = self.workspaces[0].name)
# -----------------------------------------------------------------
  @expose
  @tools.params()
  def jsrootfairy(self, *args, **kwargs):
    try:
      if len(args) >= 1:
          for s in self.sources:
            if getattr(s, 'jsonhook', None) == args[0]:
              kwargs['jsroot'] = 'true'
              data = s.getJson(*args[1:], **kwargs)
              return data
    except Exception, e:
      o = StringIO()
      traceback.print_exc(file=o)
      log("WARNING: unable to produce JSROOT json: "
          + (str(e) + "\n" + o.getvalue()).replace("\n", " ~~ "),
          severity=logging.WARNING)

    self._noResponseCaching()
    return str(e);

# -----------------------------------------------------------------
  @expose
  @tools.params()
  def jsonfairy(self, *args, **kwargs):
    """General session-independent access path for json representation
    of plot. The first subdirectory argument contains the name of the
    'source json hook' able to handle the json request.  In case of
    value of argument 'formatted' = true insread of pure JSON whole
    HTML page is returned.  The rest of the processing is given over
    to the hook."""
    try:
      if len(args) >= 1:
        for s in self.sources:
          if getattr(s, 'jsonhook', None) == args[0]:
            data = s.getJson(*args[1:], **kwargs)
            if kwargs.get('formatted') == 'true':
              template = self._maybeRefreshFile(self.templates, "json")
              variables = {'TITLE'		 : 'JSON represetation of histogram',
                           'JSON'		 : data};
              return str(Template(template, searchList=[variables]))
            else:
              return data
            break
        #if not found any...
        return 'JSON format of '+args[0]+' source plot is not supported yet.';
    except Exception, e:
      o = StringIO()
      traceback.print_exc(file=o)
      log("WARNING: unable to produce a json: "
          + (str(e) + "\n" + o.getvalue()).replace("\n", " ~~ "),
          severity=logging.WARNING)

    self._noResponseCaching()
    return str(e);


  # -----------------------------------------------------------------
  @expose
  @tools.params()
  def plotfairy(self, *args, **kwargs):
    """General session-independent access path for dynamic images.
    The first subdirectory argument contains the name of the
    "source plot hook" able to handle the plotting request.
    The rest of the processing is given over to the hook."""
    try:
      if len(args) >= 1:
        for s in self.sources:
          if getattr(s, 'plothook', None) == args[0]:
            (type, data) = s.plot(*args[1:], **kwargs)
            if type != None:
              self._noResponseCaching()
              response.headers['Content-Length'] = str(len(data))
              response.headers['Content-Type'] = type
              return data
            break
    except Exception, e:
      o = StringIO()
      traceback.print_exc(file=o)
      log("WARNING: unable to produce a plot: "
          + (str(e) + "\n" + o.getvalue()).replace("\n", " ~~ "),
          severity=logging.WARNING)

    self._noResponseCaching()
    return serve_file(self.contentpath + "/images/missing.png",
                      content_type = "image/png")

  # -----------------------------------------------------------------
  @expose
  @tools.params()
  def digest(self, *args, **kwargs):
    """Report code running in this server."""
    maxsize = max(len(str(i['srclen'])) for i in self.checksums) + 1
    maxlen = max(len(str(i['module'])) for i in self.checksums) + 2
    fmt = "%(srclen)-" + str(maxsize) \
	  + "d %(mtime)-10d  %(srcmd5)s  %(module)-" + str(maxlen) \
          + "s %(srcname)s\n"
    summary = ""

    self.checksums.sort(lambda a, b: cmp(a['srcfile'], b['srcfile']))
    for i in self.checksums:
      summary += fmt % i

    response.headers['Content-Type'] = "text/plain"
    return summary

  # -----------------------------------------------------------------
  @expose
  @tools.params()
  def authenticate(self, *args, **kwargs):
    """A hook for authenticating users.  We don't actually authenticate
    anyone here, all the authentication is done in the front-end
    reverse proxy servers.  But do provide a URL authentication can
    use to retrieve the required proxy cookies."""
    response.headers['Content-Type'] = "text/plain"
    return "Authenticated"

  # -----------------------------------------------------------------
  @expose
  @tools.params()
  @tools.gzip()
  def session(self, *args, **kwargs):
    """Main session address.  All AJAX calls to the session land here.
    The URL is of the form "[/ROOT]/session/ID[/METHOD].  We check
    the session ID is valid for this user, and the METHOD is one we
    support.  A METHOD "foo" results in call to "sessionFoo()" in
    this class.  If no METHOD is given, default to "index": generate
    the main GUI page. All other METHODs are AJAX calls from the
    client, which normally just return a JSON result object."""
    # If the URL has been truncated, just start a new session.
    if len(args) < 1:
      return self.start(workspace = self.workspaces[0].name)

    # If the URL specifies extra arguments, reply with an error page.
    sessionid = args[0]
    if len(args) > 2:
      return self._invalidURL()

    # Check the session is something we can use.  This locks the
    # session so no other thread can access it at the same time.
    session = self._getSession(sessionid)
    if not session:
      return self._invalidURL()

    # Find the session method to invoke and verify we have a good one.
    # Look for the method first in this server object, and failing
    # that in the current workspace object.  Release the session lock
    # on the way out.
    try:
      methodName = 'sessionIndex'
      if len(args) == 2:
        methodName = 'session' + args[1][0].upper() + args[1][1:]

      method = None
      workspace = session['core.workspace']
      if workspace:
        method = getattr(self._workspace(workspace), methodName, None)
      if not method:
        method = getattr(self, methodName, None)
      if not method:
        return self._invalidURL()

      # Let the session method handle the rest.
      return method(session, *args, **kwargs)
    finally:
      self._releaseSession(session)

  # -----------------------------------------------------------------
  @expose
  @tools.params()
  def urlshortener(self, *args, **kwargs):
    if (not 'url' in kwargs.keys()):
      return '{}'

    longUrl = base64.b64decode(kwargs['url'])
    shortUrl = longUrl

    try:
      connection = httplib.HTTPSConnection('tinyurl.com')
      connection.request('GET', '/api-create.php?url=%s' % longUrl)
      response = connection.getresponse()

      if (response.status == 200):
        shortUrl = response.read()
      else:
        log("WARNING: urlshortener returned status: %s for url: %s" % (response.status, longUrl), severity=logging.WARNING)
      
      connection.close()
    except:
      log("WARNING: unable to shorten URL: %s" % longUrl, severity=logging.WARNING)
    
    return '{"id": "%s"}' % shortUrl

  def sessionIndex(self, session, *args ,**kwargs):
    """Generate top level session index.  This produces the main GUI web
    page, with practically no content in it; the client will contact
    us for the content using AJAX calls."""
    return self._templatePage("index", {
	'TITLE'		 : re.sub(r"\&\#821[12];", "-", self.title),
	'HEADING'	 : self.title,
        'WORKSPACE'	 : session['core.workspace'],
        'SESSION_ID'     : session['core.name'],
        'SESSION_STATUS' : 'modifiable',
	'USER'		 : session['core.user'],
        'HOSTNAME'       : gethostname(),
	'ROOTPATH'	 : self.baseUrl
      });

  def sessionWorkspace(self, session, *args, **kwargs):
    """Switch session to another workspace."""
    workspace = self._workspace(kwargs.get('name', session['core.workspace']))
    session['core.workspace'] = workspace.name
    workspace.initialiseSession(session)
    self._saveSession(session)
    return workspace.sessionState(session)

  # -----------------------------------------------------------------
  def sessionProfileSnapshot(self, session, *args, **kwargs):
    """Drop a profile dump if running under profiler and the current
    workspace has a suitable extension (aka igprof native call)."""
    if self.instrument and self.instrument.startswith("igprof "):
      snapshot = None
      workspace = session['core.workspace']
      if workspace:
        snapshot = getattr(self._workspace(workspace), "_profilesnap", None)
      if snapshot:
        snapshot()
    return "OK"

  def sessionState(self, session, *args, **kwargs):
    """Return JSON object for the current session state.  This method is
    invoked when the GUI session page is loaded, which occurs either
    when a completely new session has been started, the "reload"
    button is pushed or the session URL was copied between browser
    windows, or the session wants a period refresh."""
    raise HTTPError(500, "Internal implementation error")
