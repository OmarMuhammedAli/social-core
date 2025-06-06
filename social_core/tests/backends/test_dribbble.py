import json

from .oauth import BaseAuthUrlTestMixin, OAuth2Test


class DribbbleOAuth2Test(OAuth2Test, BaseAuthUrlTestMixin):
    backend_path = "social_core.backends.dribbble.DribbbleOAuth2"
    user_data_url = "https://api.dribbble.com/v1/user"
    expected_username = "foobar"

    access_token_body = json.dumps({"access_token": "foobar", "token_type": "bearer"})

    user_data_body = json.dumps(
        {"id": "foobar", "username": "foobar", "name": "Foo Bar"}
    )

    def test_login(self) -> None:
        self.do_login()

    def test_partial_pipeline(self) -> None:
        self.do_partial_pipeline()
