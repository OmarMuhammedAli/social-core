import json

from .oauth import BaseAuthUrlTestMixin, OAuth2Test


class DailymotionOAuth2Test(OAuth2Test, BaseAuthUrlTestMixin):
    backend_path = "social_core.backends.dailymotion.DailymotionOAuth2"
    user_data_url = "https://api.dailymotion.com/auth/"
    expected_username = "foobar"
    access_token_body = json.dumps({"access_token": "foobar", "token_type": "bearer"})
    user_data_body = json.dumps({"id": "foobar", "screenname": "foobar"})

    def test_login(self) -> None:
        self.do_login()

    def test_partial_pipeline(self) -> None:
        self.do_partial_pipeline()
