from __future__ import annotations

import base64
import datetime
import json
from calendar import timegm
from typing import Any

import jwt
from jwt import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidTokenError,
    PyJWTError,
)
from jwt.utils import base64url_decode

from social_core.backends.oauth import BaseOAuth2
from social_core.exceptions import (
    AuthInvalidParameter,
    AuthMissingParameter,
    AuthNotImplementedParameter,
    AuthTokenError,
)
from social_core.utils import cache


class OpenIdConnectAssociation:
    """Use Association model to save the nonce by force."""

    def __init__(self, handle, secret="", issued=0, lifetime=0, assoc_type="") -> None:
        self.handle = handle  # as nonce
        self.secret = secret.encode()  # not use
        self.issued = issued  # not use
        self.lifetime = lifetime  # not use
        self.assoc_type = assoc_type  # as state


class OpenIdConnectAuth(BaseOAuth2):
    """
    Base class for Open ID Connect backends.
    Currently only the code response type is supported.

    It can also be directly instantiated as a generic OIDC backend.
    To use it you will need to set at minimum:

    SOCIAL_AUTH_OIDC_OIDC_ENDPOINT = 'https://.....'  # endpoint without /.well-known/openid-configuration
    SOCIAL_AUTH_OIDC_KEY = '<client_id>'
    SOCIAL_AUTH_OIDC_SECRET = '<client_secret>'
    """

    name = "oidc"
    # Override OIDC_ENDPOINT in your subclass to enable autoconfig of OIDC
    OIDC_ENDPOINT: str | None = None
    ID_TOKEN_MAX_AGE = 600
    DEFAULT_SCOPE = ["openid", "profile", "email"]
    EXTRA_DATA = ["id_token", "refresh_token", ("sub", "id")]
    REDIRECT_STATE = False
    REVOKE_TOKEN_METHOD = "GET"
    ID_KEY = "sub"
    USERNAME_KEY = "preferred_username"
    JWT_ALGORITHMS = ["RS256"]
    JWT_DECODE_OPTIONS: dict[str, Any] = {}
    JWT_LEEWAY: float = 1.0  # seconds
    # When these options are unspecified, server will choose via openid autoconfiguration
    ID_TOKEN_ISSUER = ""
    ACCESS_TOKEN_URL = ""
    AUTHORIZATION_URL = ""
    REVOKE_TOKEN_URL = ""
    USERINFO_URL = ""
    JWKS_URI = ""
    TOKEN_ENDPOINT_AUTH_METHOD = ""
    # Optional parameters for Authentication Request
    DISPLAY = None
    PROMPT = None
    MAX_AGE = None
    UI_LOCALES = None
    ID_TOKEN_HINT = None
    LOGIN_HINT = None
    ACR_VALUES = None

    def __init__(self, *args, **kwargs) -> None:
        self.id_token = None
        super().__init__(*args, **kwargs)

    def get_setting_config(
        self, setting_name: str, oidc_name: str, default: str
    ) -> str:
        value = self.setting(setting_name, default)
        if not value:
            value = self.oidc_config().get(oidc_name)

        if not isinstance(value, str):
            raise AuthMissingParameter(self, setting_name)
        return value

    def authorization_url(self) -> str:
        return self.get_setting_config(
            "AUTHORIZATION_URL", "authorization_endpoint", self.AUTHORIZATION_URL
        )

    def access_token_url(self) -> str:
        return self.get_setting_config(
            "ACCESS_TOKEN_URL", "token_endpoint", self.ACCESS_TOKEN_URL
        )

    def revoke_token_url(self, token, uid) -> str:
        return self.get_setting_config(
            "REVOKE_TOKEN_URL", "revocation_endpoint", self.REVOKE_TOKEN_URL
        )

    def id_token_issuer(self) -> str:
        return self.get_setting_config(
            "ID_TOKEN_ISSUER", "issuer", self.ID_TOKEN_ISSUER
        )

    def userinfo_url(self) -> str:
        return self.get_setting_config(
            "USERINFO_URL", "userinfo_endpoint", self.USERINFO_URL
        )

    def jwks_uri(self) -> str:
        return self.get_setting_config("JWKS_URI", "jwks_uri", self.JWKS_URI)

    def use_basic_auth(self) -> bool:
        method = self.setting(
            "TOKEN_ENDPOINT_AUTH_METHOD", self.TOKEN_ENDPOINT_AUTH_METHOD
        )
        if method:
            return method == "client_secret_basic"
        methods = self.oidc_config().get("token_endpoint_auth_methods_supported", [])
        return not methods or "client_secret_basic" in methods

    def oidc_endpoint(self) -> str:
        return self.setting("OIDC_ENDPOINT", self.OIDC_ENDPOINT)

    @cache(ttl=86400)
    def oidc_config(self) -> dict[Any, Any]:
        return self.get_json(self.oidc_endpoint() + "/.well-known/openid-configuration")

    @cache(ttl=86400)
    def get_jwks_keys(self):
        return self.get_remote_jwks_keys()

        # Add client secret as oct key so it can be used for HMAC signatures
        # client_id, client_secret = self.get_key_and_secret()
        # keys.append({'key': client_secret, 'kty': 'oct'})

    def get_remote_jwks_keys(self):
        response = self.request(self.jwks_uri())
        return json.loads(response.text)["keys"]

    def auth_params(self, state=None):  # noqa: C901
        """Return extra arguments needed on auth process."""
        params = super().auth_params(state)
        params["nonce"] = self.get_and_store_nonce(self.authorization_url(), state)

        display = self.setting("DISPLAY", default=self.DISPLAY)
        if display is not None:
            if not display:
                raise AuthMissingParameter(
                    self, "OpenID Connect display value cannot be empty string."
                )

            if display not in ("page", "popup", "touch", "wap"):
                raise AuthMissingParameter(
                    self, f"Invalid OpenID Connect display value: {display}"
                )

            params["display"] = display

        prompt = self.setting("PROMPT", default=self.PROMPT)
        if prompt is not None:
            if not prompt:
                raise AuthInvalidParameter(self, "prompt")

            for prompt_token in prompt.split():
                if prompt_token not in ("none", "login", "consent", "select_account"):
                    raise AuthInvalidParameter(self, "prompt")

            params["prompt"] = prompt

        max_age = self.setting("MAX_AGE", default=self.MAX_AGE)
        if max_age is not None:
            if max_age < 0:
                raise AuthInvalidParameter(self, "max_age")

            params["max_age"] = max_age

        ui_locales = self.setting("UI_LOCALES", default=self.UI_LOCALES)
        if ui_locales is not None:
            raise AuthNotImplementedParameter(self, "ui_locales")

        id_token_hint = self.setting("ID_TOKEN_HINT", default=self.ID_TOKEN_HINT)
        if id_token_hint is not None:
            raise AuthNotImplementedParameter(self, "id_token_hint")

        login_hint = self.setting("LOGIN_HINT", default=self.LOGIN_HINT)
        if login_hint is not None:
            raise AuthNotImplementedParameter(self, "login_hint")

        acr_values = self.setting("ACR_VALUES", default=self.ACR_VALUES)
        if acr_values is not None:
            raise AuthNotImplementedParameter(self, "acr_values")

        return params

    def get_and_store_nonce(self, url, state):
        # Create a nonce
        nonce = self.strategy.random_string(64)
        # Store the nonce
        association = OpenIdConnectAssociation(nonce, assoc_type=state)
        self.strategy.storage.association.store(url, association)
        return nonce

    def get_nonce(self, nonce):
        try:
            return self.strategy.storage.association.get(
                server_url=self.authorization_url(), handle=nonce
            )[0]
        except IndexError:
            pass

    def remove_nonce(self, nonce_id) -> None:
        self.strategy.storage.association.remove([nonce_id])

    def validate_claims(self, id_token) -> None:
        utc_timestamp = timegm(datetime.datetime.now(datetime.timezone.utc).timetuple())

        if "nbf" in id_token and utc_timestamp < id_token["nbf"]:
            raise AuthTokenError(self, "Incorrect id_token: nbf")

        # Verify the token was issued in the last 10 minutes
        iat_leeway = self.setting("ID_TOKEN_MAX_AGE", self.ID_TOKEN_MAX_AGE)
        if utc_timestamp > id_token["iat"] + iat_leeway:
            raise AuthTokenError(self, "Incorrect id_token: iat")

        # Validate the nonce to ensure the request was not modified
        nonce = id_token.get("nonce")
        if not nonce:
            raise AuthTokenError(self, "Incorrect id_token: nonce")

        nonce_obj = self.get_nonce(nonce)
        if nonce_obj:
            self.remove_nonce(nonce_obj.id)
        else:
            raise AuthTokenError(self, "Incorrect id_token: nonce")

    def find_valid_key(self, id_token):
        kid = jwt.get_unverified_header(id_token).get("kid")

        keys = self.get_jwks_keys()
        if kid is not None:
            for key in keys:
                if kid == key.get("kid"):
                    break
            else:
                # In case the key id is not found in the cached keys, just
                # reload the JWKS keys. Ideally this should be done by
                # invalidating the cache.
                self.get_jwks_keys.invalidate()  # type: ignore[reportFunctionMemberAccess]
                keys = self.get_jwks_keys()

        for key in keys:
            if kid is None or kid == key.get("kid"):
                if "alg" not in key:
                    key["alg"] = self.setting("JWT_ALGORITHMS", self.JWT_ALGORITHMS)[0]
                rsakey = jwt.PyJWK(key)
                message, encoded_sig = id_token.rsplit(".", 1)
                decoded_sig = base64url_decode(encoded_sig.encode("utf-8"))
                if rsakey.Algorithm.verify(
                    message.encode("utf-8"), rsakey.key, decoded_sig
                ):
                    return key
        return None

    def validate_and_return_id_token(self, id_token, access_token):
        """
        Validates the id_token according to the steps at
        http://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation.
        """
        client_id, client_secret = self.get_key_and_secret()

        key = self.find_valid_key(id_token)

        if not key:
            raise AuthTokenError(self, "Signature verification failed")

        rsakey = jwt.PyJWK(key)

        try:
            claims = jwt.decode(
                id_token,
                rsakey.key,
                algorithms=self.setting("JWT_ALGORITHMS", self.JWT_ALGORITHMS),
                audience=client_id,
                issuer=self.id_token_issuer(),
                options=self.setting("JWT_DECODE_OPTIONS", self.JWT_DECODE_OPTIONS),
                leeway=self.setting("JWT_LEEWAY", self.JWT_LEEWAY),
            )
        except ExpiredSignatureError:
            raise AuthTokenError(self, "Signature has expired")
        except InvalidAudienceError:
            # compatibility with jose error message
            raise AuthTokenError(self, "Token error: Invalid audience")
        except InvalidTokenError as error:
            raise AuthTokenError(self, str(error))
        except PyJWTError:
            raise AuthTokenError(self, "Invalid signature")

        # pyjwt does not validate OIDC claims
        # see https://github.com/jpadilla/pyjwt/pull/296
        if "at_hash" in claims and claims["at_hash"] != self.calc_at_hash(
            access_token, key["alg"]
        ):
            raise AuthTokenError(self, "Invalid access token")

        self.validate_claims(claims)

        return claims

    def request_access_token(self, *args, **kwargs):
        """
        Retrieve the access token. Also, validate the id_token and
        store it (temporarily).
        """
        response = self.get_json(*args, **kwargs)
        self.id_token = self.validate_and_return_id_token(
            response["id_token"], response["access_token"]
        )
        return response

    def user_data(self, access_token, *args, **kwargs):
        return self.get_json(
            self.userinfo_url(), headers={"Authorization": f"Bearer {access_token}"}
        )

    def get_user_details(self, response):
        username_key = self.setting("USERNAME_KEY", self.USERNAME_KEY)
        return {
            "username": response.get(username_key),
            "email": response.get("email"),
            "fullname": response.get("name"),
            "first_name": response.get("given_name"),
            "last_name": response.get("family_name"),
        }

    @staticmethod
    def calc_at_hash(access_token, algorithm):
        """
        Calculates "at_hash" claim which is not done by pyjwt.

        See https://pyjwt.readthedocs.io/en/stable/usage.html#oidc-login-flow
        """
        alg_obj = jwt.get_algorithm_by_name(algorithm)
        digest = alg_obj.compute_hash_digest(access_token.encode("utf-8"))
        return (
            base64.urlsafe_b64encode(digest[: (len(digest) // 2)])
            .decode("utf-8")
            .rstrip("=")
        )
