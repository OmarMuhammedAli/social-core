from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Any

from .backends.utils import get_backend
from .exceptions import StrategyMissingFeatureError
from .pipeline import DEFAULT_AUTH_PIPELINE, DEFAULT_DISCONNECT_PIPELINE
from .pipeline.utils import partial_load, partial_prepare, partial_store
from .store import OpenIdSessionWrapper, OpenIdStore
from .utils import PARTIAL_TOKEN_SESSION_NAME, module_member, setting_name

if TYPE_CHECKING:
    from .backends.base import BaseAuth


class BaseTemplateStrategy:
    def __init__(self, strategy) -> None:
        self.strategy = strategy

    def render(
        self,
        tpl: str | None = None,
        html: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        context = context or {}
        if tpl:
            return self.render_template(tpl, context)
        if not html:
            raise ValueError("Missing template or html parameters")
        return self.render_string(html, context)

    def render_template(self, tpl: str, context: dict[str, Any] | None) -> str:
        raise NotImplementedError("Implement in subclass")

    def render_string(self, html: str, context: dict[str, Any] | None) -> str:
        raise NotImplementedError("Implement in subclass")


class BaseStrategy:
    ALLOWED_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    DEFAULT_TEMPLATE_STRATEGY = BaseTemplateStrategy
    SESSION_SAVE_KEY = "psa_session_id"

    def __init__(self, storage=None, tpl=None) -> None:
        self.storage = storage
        self.tpl = (tpl or self.DEFAULT_TEMPLATE_STRATEGY)(self)

    def setting(self, name: str, default=None, backend: BaseAuth | None = None):
        names = [setting_name(name), name]
        if backend:
            names.insert(0, setting_name(backend.name, name))
        for value in names:
            try:
                return self.get_setting(value)
            except (AttributeError, KeyError):
                pass
        return default

    def create_user(self, *args, **kwargs):
        return self.storage.user.create_user(*args, **kwargs)

    def get_user(self, *args, **kwargs):
        return self.storage.user.get_user(*args, **kwargs)

    def session_setdefault(self, name, value):
        self.session_set(name, value)
        return self.session_get(name)

    def get_session_id(self) -> str | None:
        """
        Return session ID to be used by restore_session.
        """
        return None

    def restore_session(self, session_id: str, kwargs: dict[str, Any]) -> None:
        """
        Restores session and updates kwargs to match it.

        This is only called if get_session_id returns a value.
        """
        raise StrategyMissingFeatureError(self.__class__.__name__, "session restore")

    def openid_session_dict(self, name):
        # Many frameworks are switching the session serialization from Pickle
        # to JSON to avoid code execution risks. Flask did this from Flask
        # 0.10, Django is switching to JSON by default from version 1.6.
        #
        # Sadly python-openid stores classes instances in the session which
        # fails the JSON serialization, the classes are:
        #
        #   openid.yadis.manager.YadisServiceManager
        #   openid.consumer.discover.OpenIDServiceEndpoint
        #
        # This method will return a wrapper over the session value used with
        # openid (a dict) which will automatically keep a pickled value for the
        # mentioned classes.
        return OpenIdSessionWrapper(self.session_setdefault(name, {}))

    def to_session_value(self, val):
        return val

    def from_session_value(self, val):
        return val

    def partial_save(self, next_step, backend: BaseAuth, *args, **kwargs):
        return partial_store(self, backend, next_step, *args, **kwargs)

    def partial_prepare(self, next_step, backend: BaseAuth, *args, **kwargs):
        return partial_prepare(self, backend, next_step, *args, **kwargs)

    def partial_load(self, token):
        return partial_load(self, token)

    def clean_partial_pipeline(self, token) -> None:
        self.storage.partial.destroy(token)
        current_token_in_session = self.session_get(PARTIAL_TOKEN_SESSION_NAME)
        if current_token_in_session == token:
            self.session_pop(PARTIAL_TOKEN_SESSION_NAME)

    def openid_store(self):
        return OpenIdStore(self)

    def get_pipeline(self, backend: BaseAuth | None = None):
        return self.setting("PIPELINE", DEFAULT_AUTH_PIPELINE, backend)

    def get_disconnect_pipeline(self, backend: BaseAuth | None = None):
        return self.setting("DISCONNECT_PIPELINE", DEFAULT_DISCONNECT_PIPELINE, backend)

    def random_string(self, length: int = 12, chars: str = ALLOWED_CHARS) -> str:
        return "".join([secrets.choice(chars) for i in range(length)])

    def absolute_uri(self, path=None):
        uri = self.build_absolute_uri(path)
        if uri and self.setting("REDIRECT_IS_HTTPS"):
            uri = uri.replace("http://", "https://")
        return uri

    def get_language(self) -> str:
        """Return current language"""
        return ""

    def send_email_validation(
        self, backend: BaseAuth, email: str, partial_token: str | None = None
    ) -> str:
        email_validation = self.setting("EMAIL_VALIDATION_FUNCTION")
        send_email = module_member(email_validation)
        code = self.storage.code.make_code(email)
        send_email(self, backend, code, partial_token)
        return code

    def validate_email(self, email: str, code: str) -> bool:
        verification_code = self.storage.code.get_code(code)
        if not verification_code or verification_code.code != code:
            return False
        if verification_code.email != email:
            return False
        if verification_code.verified:
            return False
        verification_code.verify()
        return True

    def render_html(
        self,
        tpl: str | None = None,
        html: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Render given template or raw html with given context"""
        return self.tpl.render(tpl, html, context)

    def authenticate(self, backend: BaseAuth, *args, **kwargs):
        """Trigger the authentication mechanism tied to the current
        framework"""
        kwargs["strategy"] = self
        kwargs["storage"] = self.storage
        kwargs["backend"] = backend
        args, kwargs = self.clean_authenticate_args(*args, **kwargs)
        return backend.authenticate(*args, **kwargs)

    def clean_authenticate_args(self, *args, **kwargs):
        """Take authenticate arguments and return a "cleaned" version
        of them"""
        return args, kwargs

    def get_backends(self):
        """Return configured backends"""
        return self.setting("AUTHENTICATION_BACKENDS", [])

    def get_backend_class(self, name):
        """Return a configured backend class"""
        return get_backend(self.get_backends(), name)

    def get_backend(self, name, redirect_uri=None, *args, **kwargs):
        """Return a configured backend instance"""
        Backend = self.get_backend_class(name)
        return Backend(self, redirect_uri=redirect_uri, *args, **kwargs)

    # Implement the following methods on strategies sub-classes

    def redirect(self, url):
        """Return a response redirect to the given URL"""
        raise NotImplementedError("Implement in subclass")

    def get_setting(self, name):
        """Return value for given setting name"""
        raise NotImplementedError("Implement in subclass")

    def html(self, content):
        """Return HTTP response with given content"""
        raise NotImplementedError("Implement in subclass")

    def request_data(self, merge=True):
        """Return current request data (POST or GET)"""
        raise NotImplementedError("Implement in subclass")

    def request_host(self) -> str:
        """Return current host value"""
        raise NotImplementedError("Implement in subclass")

    def session_get(self, name, default=None):
        """Return session value for given key"""
        raise NotImplementedError("Implement in subclass")

    def session_set(self, name, value):
        """Set session value for given key"""
        raise NotImplementedError("Implement in subclass")

    def session_pop(self, name):
        """Pop session value for given key"""
        raise NotImplementedError("Implement in subclass")

    def build_absolute_uri(self, path: str | None = None) -> str:
        """Build absolute URI with given (optional) path"""
        raise NotImplementedError("Implement in subclass")

    def request_is_secure(self) -> bool:
        """Is the request using HTTPS?"""
        raise NotImplementedError("Implement in subclass")

    def request_path(self) -> str:
        """path of the current request"""
        raise NotImplementedError("Implement in subclass")

    def request_port(self) -> int:
        """Port in use for this request"""
        raise NotImplementedError("Implement in subclass")

    def request_get(self):
        """Request GET data"""
        raise NotImplementedError("Implement in subclass")

    def request_post(self):
        """Request POST data"""
        raise NotImplementedError("Implement in subclass")
