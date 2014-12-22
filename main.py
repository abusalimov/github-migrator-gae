#!/usr/bin/env python
"""
GAE app for gathering GitHub access tokens and Google emails.
Used for migrating issues from Google Code to GitHub.
"""

__author__ = "Eldar Abusalimov"


import json
import os
import urllib
import hashlib

import jinja2
import webapp2
from webapp2_extras import sessions
from google.appengine.ext import ndb

from authomatic import Authomatic
from authomatic import provider_id
from authomatic.adapters import Webapp2Adapter
from authomatic.providers import oauth2, BaseProvider
from authomatic.exceptions import BaseError
from authomatic.exceptions import HTTPError

import authomatic.core
import authomatic.providers
authomatic.providers.BaseProvider._logger = authomatic.core._logger  # XXX

import config


# Instantiate Authomatic.
auth = Authomatic(config={
        'google': {
            'id': authomatic.provider_id(),
            'class_': oauth2.Google,
            'consumer_key':    config.GOOGLE_AUTH['client_id'],
            'consumer_secret': config.GOOGLE_AUTH['client_secret'],
            'scope': ['email'],
        },

        'github': {
            'id': authomatic.provider_id(),
            'class_': oauth2.GitHub,
            'consumer_key':    config.GITHUB_AUTH['client_id'],
            'consumer_secret': config.GITHUB_AUTH['client_secret'],
            'scope': ['user:email', 'public_repo'],
        },
    },
    secret=config.SECRET)

def _monkey_patch_init_to_prompt_account(goog):
    orig_init = goog.__init__
    def init_with_prompting(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        self.user_authorization_params['prompt'] = 'select_account'
    goog.__init__ = init_with_prompting
_monkey_patch_init_to_prompt_account(oauth2.Google)


DEFAULT_PROJECT_NAME = 'project'
USER_PROPS           = ['info', 'emails']
USER_INFO_PROPS      = ['id', 'username', 'name', 'link', 'picture']


def project_key(project_name=DEFAULT_PROJECT_NAME):
    """Constructs a Datastore key for a Project entity with project_name."""
    return ndb.Key('Project', project_name)

class User(ndb.Model):
    """Models an individual Project entry."""
    info   = ndb.JsonProperty(indexed=False)
    token  = ndb.StringProperty(indexed=False)
    emails = ndb.StringProperty(repeated=True)
    date   = ndb.DateTimeProperty(auto_now_add=True)

    @classmethod
    def query_all(cls, ancestor_key=project_key()):
        return cls.query(ancestor=ancestor_key).order(-cls.date)


templates_path = os.path.join(os.path.dirname(__file__), 'templates')
jinja2_env = jinja2.Environment(loader=jinja2.FileSystemLoader(templates_path))

class IndexHandler(webapp2.RequestHandler):
    INDEX_HTML = jinja2_env.get_template('index.html').render(config=config)
    def get(self):
        self.response.write(self.INDEX_HTML)


class GenericError(BaseError):
    def __init__(self, error):
        super(GenericError, self).__init__(str(error))


class BaseHandler(webapp2.RequestHandler):

    @webapp2.cached_property
    def session(self):
        # Returns a session using the default cookie key.
        return self.session_store.get_session(backend='memcache')

    def dispatch(self):
        # Get a session store for this request.
        self.session_store = sessions.get_store(request=self.request)

        try:
            # Dispatch the request.
            webapp2.RequestHandler.dispatch(self)
        finally:
            # Save all sessions.
            self.session_store.save_sessions(self.response)

    @webapp2.cached_property
    def user(self):
        user_key_id = self.session.get('user_key_id')
        if user_key_id:
            return User.get_by_id(user_key_id, parent=project_key())

    def put_user(self, user):
        if user:
            self.session['user_key_id'] = user.key.id()
        else:
            self.session.pop('user_key_id', None)

    def state_dict(self, **defaults):
        if self.user:
            defaults.update(user=self.user.to_dict(include=USER_PROPS))
        return defaults

    def get_user_by_email(self, email):
        users_query = User.query_all().filter(User.emails == email)
        users = list(users_query.fetch())
        if not users:
            return
        else:
            assert len(users) == 1
        return users[0]

    def add_user_email(self, user, email):
        old_user = self.get_user_by_email(email)
        if old_user:
            old_user.emails.remove(email)
            old_user.put()

        user.emails.append(email)

    @webapp2.cached_property
    def admin_user(self):
        user = self.get_user_by_email(config.ADMIN_EMAIL)
        if not user:
            self.abort(403)
        return user

    @webapp2.cached_property
    def admin_code(self):
        sha = hashlib.sha1()
        sha.update(config.ADMIN_EMAIL)
        sha.update(config.SECRET)
        sha.update(self.admin_user.token)
        return sha.hexdigest()

    @webapp2.cached_property
    def has_admin_rights(self):
        return (self.user == self.admin_user or
                self.request.get('code') == self.admin_code)

    def ensure_admin(self):
        if not self.has_admin_rights:
            self.abort(403)


class FormattedResultHandler(BaseHandler):

    def get(self, result_format):
        result = self.handle()
        self.respond(result, result_format)

    def handle(self):
        pass

    def respond(self, result, result_format):
        if result_format and result_format[0] == '.':
            result_format = result_format[1:]
        assert result_format in ('json', 'js') or not result_format, result_format

        def obj_to_dict(obj):
            if hasattr(obj, 'to_dict'):
                return obj.to_dict()

        result_json = json.dumps(result, default=obj_to_dict,
                                 indent=(4 if result_format == 'json' else None))

        if result_format == 'json':
            self.response.content_type = 'application/json'
            response_str = result_json

        elif result_format == 'js':
            self.response.content_type = 'application/javascript'
            response_str = ("handleState({result_json});"
                            .format(**locals()))

        else:
            response_str = """
            <!DOCTYPE html>
            <html>
                <head>
                    <script type="text/javascript">
                        try {{
                            window.opener.handleState({result_json});
                        }} catch(e) {{ }}
                        window.close();
                    </script>
                </head>
                <body></body>
            </html>
            """.format(**locals())

        self.response.write(response_str)


class StateHandler(FormattedResultHandler):
    def handle(self):
        return self.state_dict()

class LoginHandler(FormattedResultHandler):

    def any(self, provider_name='', result_format=None):
        # It all begins with login.
        def clean_session(result):  # XXX
            self.session.pop(auth.prefix, None)
        result = auth.login(Webapp2Adapter(self), provider_name,
                                  session=self.session,
                                  session_saver=self.session.on_update,
                                  callback=clean_session)
        if not result:
            # Do not write anything to the response if there is no result!
            return

        if result.user:
            if not result.error:
                try:
                    self.fetch_user_info(result)
                except BaseError as e:
                    result.error = e
                except Exception as e:
                    result.error = GenericError(e)

            if not result.error:
                self.login_successful(result)

        self.respond(self.state_dict(error=result.error), result_format)

    def fetch_user_info(self, result):
        response = result.user.update()
        response._data = result.user.data  # XXX
        self.ensure_response_http_ok(response)

        if result.provider.name == 'github':
            emails_url = oauth2.GitHub.user_info_url + '/emails'
            response = auth.access(result.user.credentials, emails_url)
            self.ensure_response_http_ok(response)
            result.user.github_emails = response.data or []

    def ensure_response_http_ok(self, response):
        if response.status >= 400:
            raise HTTPError(response.data
                            .get('error', {})
                            .get('message', response.data))

    def login_successful(self, result):
        if result.provider.name == 'github':
            user = User.get_or_insert(result.user.id, parent=project_key())
            user.token = result.user.credentials.token
            user.info = {prop: getattr(result.user, prop, None)
                         for prop in USER_INFO_PROPS}

            for entry in result.user.github_emails:
                if entry['verified']:
                    self.add_user_email(user, entry['email'])

            user.put()
            self.put_user(user)

        elif result.provider.name == 'google':
            if result.user.email and self.user:
                self.add_user_email(self.user, result.user.email.lower())
                self.user.put()

class LogoutHandler(FormattedResultHandler):
    def handle(self):
        self.session.clear()
        return self.state_dict()

class RemoveEmailHandler(FormattedResultHandler):
    def handle(self):
        if self.user:
            email = self.request.get('email').lower()
            if email in self.user.emails:
                self.user.emails.remove(email)
                self.user.put()

        return self.state_dict()


class AdminCodeHandler(FormattedResultHandler):
    def handle(self):
        self.ensure_admin()
        return dict(code=self.admin_code)

class UsersHandler(FormattedResultHandler):
    def handle(self):
        self.ensure_admin()

        users_query = User.query(ancestor=project_key()).order(-User.date)
        users = users_query.fetch()

        return [user.to_dict(include=USER_PROPS+['token']) for user in users]

class EmailsHandler(FormattedResultHandler):
    def handle(self):
        self.ensure_admin()

        users_query = User.query(ancestor=project_key()).order(-User.date)
        users = users_query.fetch()

        return {email: user.info['username'] for user in users
                for email in user.emails}

class ResetHandler(FormattedResultHandler):
    def handle(self):
        self.ensure_admin()

        users_query = User.query_all()
        for user in users_query.fetch():
            user.key.delete()

        self.session.clear()
        return self.state_dict()


# Instantiate the webapp2 WSGI application.
app = webapp2.WSGIApplication([
        webapp2.Route(r'/', IndexHandler),

        webapp2.Route(r'/app/state<result_format:(\.(json|js))?>', StateHandler),
        webapp2.Route(r'/app/login/', LoginHandler, handler_method='any'),
        webapp2.Route(r'/app/login/<provider_name:.*?><result_format:(\.(json|js))?>',
                      LoginHandler, handler_method='any'),
        webapp2.Route(r'/app/logout<result_format:(\.(json|js))?>', LogoutHandler),
        webapp2.Route(r'/app/remove<result_format:(\.(json|js))?>', RemoveEmailHandler),
        webapp2.Route(r'/app/admin<result_format:(\.(json|js))?>', AdminCodeHandler),
        webapp2.Route(r'/app/users<result_format:(\.(json|js))?>', UsersHandler),
        webapp2.Route(r'/app/emails<result_format:(\.(json|js))?>', EmailsHandler),
        webapp2.Route(r'/app/reset<result_format:(\.(json|js))?>', ResetHandler),
    ],
    config={
        'webapp2_extras.sessions': {
            'secret_key': config.SECRET,
            'backends': {
                'datastore':    'webapp2_extras.appengine.sessions_ndb.DatastoreSessionFactory',
                'memcache':     'webapp2_extras.appengine.sessions_memcache.MemcacheSessionFactory',
                'securecookie': 'webapp2_extras.sessions.SecureCookieSessionFactory',
            }
        },
    },
    debug=True)
