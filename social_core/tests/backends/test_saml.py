import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests
import responses

try:
    from onelogin.saml2.utils import OneLogin_Saml2_Utils

    SAML_MODULE_ENABLED = True
except ImportError:
    SAML_MODULE_ENABLED = False

from social_core.exceptions import AuthMissingParameter

from .base import BaseBackendTest

DATA_DIR = Path(__file__).parent / "data"


@unittest.skipIf(
    "__pypy__" in sys.builtin_module_names, "dm.xmlsec not compatible with pypy"
)
@unittest.skipUnless(SAML_MODULE_ENABLED, "Only run if onelogin.saml2 is installed")
class SAMLTest(BaseBackendTest):
    backend_path = "social_core.backends.saml.SAMLAuth"
    expected_username = "myself"
    response_fixture = "saml_response.txt"

    def extra_settings(self):
        file = DATA_DIR / "saml_config.json"
        config_str = file.read_text()
        return json.loads(config_str)

    def setUp(self) -> None:
        """Patch the time so that we can replay canned
        request/response pairs"""
        super().setUp()

        @staticmethod
        def fixed_time():
            return OneLogin_Saml2_Utils.parse_SAML_to_time("2015-05-09T03:57:22Z")

        now_patch = patch.object(OneLogin_Saml2_Utils, "now", fixed_time)
        now_patch.start()
        self.addCleanup(now_patch.stop)

    def install_http_intercepts(self, start_url, return_url) -> None:
        # When we request start_url
        # (https://idp.testshib.org/idp/profile/SAML2/Redirect/SSO...)
        # we will eventually get a redirect back, with SAML assertion
        # data in the query string.  A pre-recorded correct response
        # is kept in this .txt file:
        file = DATA_DIR / self.response_fixture
        response_url = file.read_text()
        responses.add(
            responses.GET,
            start_url,
            status=301,
            headers={"Location": response_url},
        )
        responses.add(responses.GET, return_url, status=200, body="foobar")

    def do_start(self):
        start_url = self.backend.start().url
        # Modify the start URL to make the SAML request consistent
        # from test to test:
        start_url = self.modify_start_url(start_url)
        # If the SAML Identity Provider recognizes the user, we will
        # be redirected back to:
        return_url = self.backend.redirect_uri
        self.install_http_intercepts(start_url, return_url)
        response = requests.get(start_url, timeout=1)
        self.assertTrue(response.url.startswith(return_url))
        self.assertEqual(response.text, "foobar")
        query_values = {
            k: v[0] for k, v in parse_qs(urlparse(response.url).query).items()
        }
        self.assertNotIn(" ", query_values["SAMLResponse"])
        self.strategy.set_request_data(query_values, self.backend)
        return self.backend.complete()

    def test_metadata_generation(self) -> None:
        """Test that we can generate the metadata without error"""
        xml, errors = self.backend.generate_metadata_xml()
        self.assertEqual(len(errors), 0)
        self.assertEqual(xml.decode()[0], "<")

    def test_login_with_next_url(self) -> None:
        """
        Test that we login and then redirect to the "next" URL.
        """
        # pretend we've started with a URL like /login/saml/?idp=testshib&next=/foo/bar
        self.strategy.set_request_data(
            {"idp": "testshib", "next": "/foo/bar"}, self.backend
        )
        self.do_login()
        # The core `do_complete` action assumes the "next" URL is stored in session state or the request data.
        self.assertEqual(self.strategy.session_get("next"), "/foo/bar")

    def test_login_no_next_url(self) -> None:
        """
        Test that we handle "next" being omitted from the request data and RelayState.
        """
        self.response_fixture = "saml_response_no_next_url.txt"

        # pretend we've started with a URL like /login/saml/?idp=testshib
        self.strategy.set_request_data({"idp": "testshib"}, self.backend)
        self.do_login()
        self.assertEqual(self.strategy.session_get("next"), None)

    def test_login_with_legacy_relay_state(self) -> None:
        """
        Test that we handle legacy RelayState (i.e. just the IDP name, not a JSON object).

        This is the form that RelayState had in prior versions of this library. It should be supported for backwards
        compatibility.
        """
        self.response_fixture = "saml_response_legacy.txt"

        self.strategy.set_request_data({"idp": "testshib"}, self.backend)
        self.do_login()

    def test_login_no_idp_in_initial_request(self) -> None:
        """
        Logging in without an idp param should raise AuthMissingParameter
        """
        with self.assertRaises(AuthMissingParameter):
            self.do_start()

    def test_login_no_idp_in_saml_response(self) -> None:
        """
        The RelayState should always contain a JSON object with an "idp" key, or be just the IDP name as a string.
        This tests that an exception is raised if it is a JSON object, but is missing the "idp" key.
        """
        self.response_fixture = "saml_response_no_idp_name.txt"

        with self.assertRaises(AuthMissingParameter):
            self.do_start()

    def modify_start_url(self, start_url):
        """
        Given a SAML redirect URL, parse it and change the ID to
        a consistent value, so the request is always identical.
        """
        # Parse the SAML Request URL to get the XML being sent to TestShib
        url_parts = urlparse(start_url)
        query = {k: v[0] for (k, v) in parse_qs(url_parts.query).items()}
        xml = OneLogin_Saml2_Utils.decode_base64_and_inflate(query["SAMLRequest"])
        # Modify the XML:
        xml = xml.decode()
        xml, changed = re.subn(r'ID="[^"]+"', 'ID="TEST_ID"', xml)
        self.assertEqual(changed, 1)
        # Update the URL to use the modified query string:
        query["SAMLRequest"] = OneLogin_Saml2_Utils.deflate_and_base64_encode(xml)
        url_parts = list(url_parts)
        url_parts[4] = urlencode(query)
        return urlunparse(url_parts)
