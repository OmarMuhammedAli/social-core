"""
VK.com OpenAPI, OAuth2 and Iframe application OAuth2 backends, docs at:
    https://python-social-auth.readthedocs.io/en/latest/backends/vk.html
"""

from __future__ import annotations

import json
from hashlib import md5
from time import time
from typing import Any, cast

from social_core.exceptions import AuthException, AuthTokenRevoked
from social_core.utils import parse_qs

from .base import BaseAuth
from .oauth import BaseOAuth2


def vk_sig(payload: str) -> str:
    """
    Calculates signature using md5.

    https://dev.vk.com/en/api/open-api/getting-started#Authorization%20on%20the%20Remote%20Side
    """
    return md5(payload.encode("utf-8")).hexdigest()  # noqa: S324


class VKontakteOpenAPI(BaseAuth):
    """VK.COM OpenAPI authentication backend"""

    name = "vk-openapi"
    ID_KEY = "id"

    def get_user_details(self, response):
        """Return user details from VK.com request"""
        nickname = response.get("nickname") or ""
        fullname, first_name, last_name = self.get_user_names(
            first_name=response.get("first_name", [""])[0],
            last_name=response.get("last_name", [""])[0],
        )
        return {
            "username": response["id"] if len(nickname) == 0 else nickname,
            "email": "",
            "fullname": fullname,
            "first_name": first_name,
            "last_name": last_name,
        }

    def user_data(self, access_token, *args, **kwargs):
        return self.data

    def auth_html(self) -> str:
        """Returns local VK authentication page, not necessary for
        VK to authenticate.
        """
        ctx = {
            "VK_APP_ID": self.setting("APP_ID"),
            "VK_COMPLETE_URL": self.redirect_uri,
        }
        local_html = self.setting("LOCAL_HTML", "vkontakte.html")
        return self.strategy.render_html(tpl=local_html, context=ctx)

    def auth_complete(self, *args, **kwargs):
        """Performs check of authentication in VKontakte, returns User if
        succeeded"""
        session_value = self.strategy.session_get("vk_app_" + self.setting("APP_ID"))
        if "id" not in self.data or not session_value:
            raise ValueError("VK.com authentication is not completed")

        mapping = parse_qs(session_value)
        check_str = "".join(
            item + "=" + mapping[item] for item in ["expire", "mid", "secret", "sid"]
        )

        key, secret = self.get_key_and_secret()
        vk_hash = vk_sig(check_str + secret)
        if vk_hash != mapping["sig"] or int(mapping["expire"]) < time():
            raise ValueError("VK.com authentication failed: Invalid Hash")

        kwargs.update({"backend": self, "response": self.user_data(mapping["mid"])})
        return self.strategy.authenticate(*args, **kwargs)

    def uses_redirect(self) -> bool:
        """VK.com does not require visiting server url in order
        to do authentication, so auth_xxx methods are not needed to be called.
        Their current implementation is just an example"""
        return False


class VKOAuth2(BaseOAuth2):
    """VKOAuth2 authentication backend"""

    name = "vk-oauth2"
    ID_KEY = "id"
    AUTHORIZATION_URL = "https://oauth.vk.com/authorize"
    ACCESS_TOKEN_URL = "https://oauth.vk.com/access_token"
    EXTRA_DATA = [("id", "id"), ("expires_in", "expires")]

    def get_user_details(self, response):
        """Return user details from VK.com account"""
        fullname, first_name, last_name = self.get_user_names(
            first_name=response.get("first_name"), last_name=response.get("last_name")
        )
        return {
            "username": response.get("screen_name"),
            "email": response.get("email", ""),
            "fullname": fullname,
            "first_name": first_name,
            "last_name": last_name,
        }

    def user_data(self, access_token, *args, **kwargs):
        """Loads user data from service"""
        request_data = [
            "first_name",
            "last_name",
            "screen_name",
            "nickname",
            "photo",
            *self.setting("EXTRA_DATA", []),
        ]

        fields = ",".join(set(request_data))
        response = self.vk_api(
            "users.get",
            {
                "access_token": access_token,
                "fields": fields,
            },
        )

        if response and response.get("error"):
            error = response["error"]
            msg = error.get("error_msg", "Unknown error")
            if error.get("error_code") == 5:
                raise AuthTokenRevoked(self, msg)
            raise AuthException(self, msg)

        if response:
            data = cast("list[dict[str, str | None]]", response.get("response"))[0]
            data["user_photo"] = data.get("photo")  # Backward compatibility
            return data
        return {}

    def vk_api(self, method: str, data: dict[str, str]) -> dict[Any, Any] | None:
        """
        Calls VK.com OpenAPI method, check:
            https://vk.com/apiclub
            http://goo.gl/yLcaa
        """
        # We need to perform server-side call if no access_token
        data["v"] = self.setting("API_VERSION", "5.131")
        if "access_token" not in data:
            key, secret = self.get_key_and_secret()
            if "api_id" not in data:
                data["api_id"] = key

            data["method"] = method
            data["format"] = "json"
            url = "https://api.vk.com/api.php"
            param_list = sorted(item + "=" + data[item] for item in data)
            data["sig"] = vk_sig("".join(param_list) + secret)
        else:
            url = "https://api.vk.com/method/" + method

        try:
            return self.get_json(url, params=data)
        except (TypeError, KeyError, OSError, ValueError, IndexError):
            return None


class VKAppOAuth2(VKOAuth2):
    """VK.com Application Authentication support"""

    name = "vk-app"

    def auth_complete(self, *args, **kwargs):
        required_params = ("is_app_user", "viewer_id", "access_token", "api_id")
        if not all(param in self.data for param in required_params):
            return None

        auth_key = self.data.get("auth_key")

        # Verify signature, if present
        key, secret = self.get_key_and_secret()
        if auth_key:
            check_key = vk_sig("_".join([key, self.data.get("viewer_id"), secret]))
            if check_key != auth_key:
                raise ValueError("VK.com authentication failed: invalid auth key")

        user_check = self.setting("USERMODE")
        user_id = self.data.get("viewer_id")
        if user_check is not None:
            user_check = int(user_check)
            if user_check == 1:
                is_user = self.data.get("is_app_user")
            elif user_check == 2:
                is_user = self.vk_api("isAppUser", {"user_id": user_id}).get(
                    "response", 0
                )
            if not int(is_user):
                return None

        auth_data = {
            "auth": self,
            "backend": self,
            "request": self.strategy.request_data(),
            "response": {
                self.ID_KEY: user_id,
            },
        }
        auth_data["response"].update(
            json.loads(auth_data["request"]["api_result"])["response"][0]
        )
        return self.strategy.authenticate(*args, **auth_data)
