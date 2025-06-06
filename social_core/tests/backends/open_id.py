# pyright: reportAttributeAccessIssue=false

from html.parser import HTMLParser

import requests
import responses

from social_core.backends.utils import load_backends
from social_core.tests.models import (
    TestAssociation,
    TestNonce,
    TestStorage,
    TestUserSocialAuth,
    User,
)
from social_core.tests.strategy import TestStrategy
from social_core.utils import module_member, parse_qs

from .base import BaseBackendTest


class FormHTMLParser(HTMLParser):
    form = {}
    inputs = {}

    def handle_starttag(self, tag, attrs) -> None:
        attrs = dict(attrs)
        if tag == "form":
            self.form.update(attrs)
        elif tag == "input" and "name" in attrs:
            self.inputs[attrs["name"]] = attrs["value"]


class OpenIdTest(BaseBackendTest):
    def setUp(self) -> None:
        responses.start()
        Backend = module_member(self.backend_path)
        self.strategy = TestStrategy(TestStorage)
        self.complete_url = self.raw_complete_url.format(Backend.name)
        self.backend = Backend(self.strategy, redirect_uri=self.complete_url)
        self.strategy.set_settings(
            {
                "SOCIAL_AUTH_AUTHENTICATION_BACKENDS": (
                    self.backend_path,
                    "social_core.tests.backends.test_broken.BrokenBackendAuth",
                )
            }
        )
        # Force backends loading to trash PSA cache
        load_backends(
            self.strategy.get_setting("SOCIAL_AUTH_AUTHENTICATION_BACKENDS"),
            force_load=True,
        )

    def tearDown(self) -> None:
        self.strategy = None
        User.reset_cache()
        TestUserSocialAuth.reset_cache()
        TestNonce.reset_cache()
        TestAssociation.reset_cache()
        responses.stop()
        responses.reset()

    def get_form_data(self, html):
        parser = FormHTMLParser()
        parser.feed(html)
        return parser.form, parser.inputs

    def openid_url(self):
        return self.backend.openid_url()

    def post_start(self) -> None:
        pass

    def do_start(self):
        responses.add(
            responses.GET,
            self.openid_url(),
            status=200,
            body=self.discovery_body,
            content_type="application/xrds+xml",
        )
        start = self.backend.start()
        self.post_start()
        form, inputs = self.get_form_data(start)
        action = form.get("action")
        assert action, "The form action must be set in the test"
        responses.add(responses.POST, action, status=200, body=self.server_response)
        response = requests.post(action, data=inputs, timeout=1)
        self.strategy.set_request_data(parse_qs(response.content), self.backend)
        responses.add(
            responses.POST, form.get("action"), status=200, body="is_valid:true\n"
        )
        return self.backend.complete()
