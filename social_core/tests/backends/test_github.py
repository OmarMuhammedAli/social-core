import json

import responses

from social_core.exceptions import AuthFailed

from .oauth import BaseAuthUrlTestMixin, OAuth2Test


class GithubOAuth2Test(OAuth2Test, BaseAuthUrlTestMixin):
    backend_path = "social_core.backends.github.GithubOAuth2"
    user_data_url = "https://api.github.com/user"
    expected_username = "foobar"
    access_token_body = json.dumps(
        {
            "access_token": "foobar",
            "token_type": "bearer",
            "expires_in": 28800,
            "refresh_token": "foobar-refresh-token",
        }
    )
    refresh_token_body = json.dumps(
        {
            "access_token": "foobar-new-token",
            "token_type": "bearer",
            "expires_in": 28800,
            "refresh_token": "foobar-new-refresh-token",
            "refresh_token_expires_in": 15897600,
            "scope": "",
        }
    )
    user_data_body = json.dumps(
        {
            "login": "foobar",
            "id": 1,
            "avatar_url": "https://github.com/images/error/foobar_happy.gif",
            "gravatar_id": "somehexcode",
            "url": "https://api.github.com/users/foobar",
            "name": "monalisa foobar",
            "company": "GitHub",
            "blog": "https://github.com/blog",
            "location": "San Francisco",
            "email": "foo@bar.com",
            "hireable": False,
            "bio": "There once was...",
            "public_repos": 2,
            "public_gists": 1,
            "followers": 20,
            "following": 0,
            "html_url": "https://github.com/foobar",
            "created_at": "2008-01-14T04:33:35Z",
            "type": "User",
            "total_private_repos": 100,
            "owned_private_repos": 100,
            "private_gists": 81,
            "disk_usage": 10000,
            "collaborators": 8,
            "plan": {
                "name": "Medium",
                "space": 400,
                "collaborators": 10,
                "private_repos": 20,
            },
        }
    )

    def do_login(self):
        user = super().do_login()
        social = user.social[0]

        self.assertIsNotNone(social.extra_data["expires"])
        self.assertIsNotNone(social.extra_data["refresh_token"])

        return user

    def test_login(self) -> None:
        self.do_login()

    def test_partial_pipeline(self) -> None:
        self.do_partial_pipeline()

    def test_refresh_token(self) -> None:
        user, social = self.do_refresh_token()
        self.assertEqual(social.extra_data["access_token"], "foobar-new-token")


class GithubOAuth2NoEmailTest(GithubOAuth2Test):
    user_data_body = json.dumps(
        {
            "login": "foobar",
            "id": 1,
            "avatar_url": "https://github.com/images/error/foobar_happy.gif",
            "gravatar_id": "somehexcode",
            "url": "https://api.github.com/users/foobar",
            "name": "monalisa foobar",
            "company": "GitHub",
            "blog": "https://github.com/blog",
            "location": "San Francisco",
            "email": "",
            "hireable": False,
            "bio": "There once was...",
            "public_repos": 2,
            "public_gists": 1,
            "followers": 20,
            "following": 0,
            "html_url": "https://github.com/foobar",
            "created_at": "2008-01-14T04:33:35Z",
            "type": "User",
            "total_private_repos": 100,
            "owned_private_repos": 100,
            "private_gists": 81,
            "disk_usage": 10000,
            "collaborators": 8,
            "plan": {
                "name": "Medium",
                "space": 400,
                "collaborators": 10,
                "private_repos": 20,
            },
        }
    )

    def test_login(self) -> None:
        url = "https://api.github.com/user/emails"
        responses.add(
            responses.GET,
            url,
            status=200,
            body=json.dumps(["foo@bar.com"]),
            content_type="application/json",
        )
        self.do_login()

    def test_login_next_format(self) -> None:
        url = "https://api.github.com/user/emails"
        responses.add(
            responses.GET,
            url,
            status=200,
            body=json.dumps([{"email": "foo@bar.com"}]),
            content_type="application/json",
        )
        self.do_login()

    def test_partial_pipeline(self) -> None:
        url = "https://api.github.com/user/emails"
        responses.add(
            responses.GET,
            url,
            status=200,
            body=json.dumps([{"email": "foo@bar.com"}]),
            content_type="application/json",
        )
        self.do_partial_pipeline()

    def test_refresh_token(self) -> None:
        url = "https://api.github.com/user/emails"
        responses.add(
            responses.GET,
            url,
            status=200,
            body=json.dumps([{"email": "foo@bar.com"}]),
            content_type="application/json",
        )
        self.do_refresh_token()


class GithubOrganizationOAuth2Test(GithubOAuth2Test):
    backend_path = "social_core.backends.github.GithubOrganizationOAuth2"

    def auth_handlers(self, start_url):
        url = "https://api.github.com/orgs/foobar/members/foobar"
        responses.add(responses.GET, url, status=204, body="")
        return super().auth_handlers(start_url)

    def test_login(self) -> None:
        self.strategy.set_settings({"SOCIAL_AUTH_GITHUB_ORG_NAME": "foobar"})
        self.do_login()

    def test_partial_pipeline(self) -> None:
        self.strategy.set_settings({"SOCIAL_AUTH_GITHUB_ORG_NAME": "foobar"})
        self.do_partial_pipeline()

    def test_refresh_token(self) -> None:
        self.strategy.set_settings({"SOCIAL_AUTH_GITHUB_ORG_NAME": "foobar"})
        self.do_refresh_token()


class GithubOrganizationOAuth2FailTest(GithubOAuth2Test):
    backend_path = "social_core.backends.github.GithubOrganizationOAuth2"

    def auth_handlers(self, start_url):
        url = "https://api.github.com/orgs/foobar/members/foobar"
        responses.add(
            responses.GET,
            url,
            status=404,
            body='{"message": "Not Found"}',
            content_type="application/json",
        )
        return super().auth_handlers(start_url)

    def test_login(self) -> None:
        self.strategy.set_settings({"SOCIAL_AUTH_GITHUB_ORG_NAME": "foobar"})
        with self.assertRaises(AuthFailed):
            self.do_login()

    def test_partial_pipeline(self) -> None:
        self.strategy.set_settings({"SOCIAL_AUTH_GITHUB_ORG_NAME": "foobar"})
        with self.assertRaises(AuthFailed):
            self.do_partial_pipeline()

    def test_refresh_token(self) -> None:
        self.strategy.set_settings({"SOCIAL_AUTH_GITHUB_ORG_NAME": "foobar"})
        with self.assertRaises(AuthFailed):
            self.do_refresh_token()


class GithubTeamOAuth2Test(GithubOAuth2Test):
    backend_path = "social_core.backends.github.GithubTeamOAuth2"

    def auth_handlers(self, start_url):
        url = "https://api.github.com/teams/123/members/foobar"
        responses.add(responses.GET, url, status=204, body="")
        return super().auth_handlers(start_url)

    def test_login(self) -> None:
        self.strategy.set_settings({"SOCIAL_AUTH_GITHUB_TEAM_ID": "123"})
        self.do_login()

    def test_partial_pipeline(self) -> None:
        self.strategy.set_settings({"SOCIAL_AUTH_GITHUB_TEAM_ID": "123"})
        self.do_partial_pipeline()

    def test_refresh_token(self) -> None:
        self.strategy.set_settings({"SOCIAL_AUTH_GITHUB_TEAM_ID": "123"})
        self.do_refresh_token()


class GithubTeamOAuth2FailTest(GithubOAuth2Test):
    backend_path = "social_core.backends.github.GithubTeamOAuth2"

    def auth_handlers(self, start_url):
        url = "https://api.github.com/teams/123/members/foobar"
        responses.add(
            responses.GET,
            url,
            status=404,
            body='{"message": "Not Found"}',
            content_type="application/json",
        )
        return super().auth_handlers(start_url)

    def test_login(self) -> None:
        self.strategy.set_settings({"SOCIAL_AUTH_GITHUB_TEAM_ID": "123"})
        with self.assertRaises(AuthFailed):
            self.do_login()

    def test_partial_pipeline(self) -> None:
        self.strategy.set_settings({"SOCIAL_AUTH_GITHUB_TEAM_ID": "123"})
        with self.assertRaises(AuthFailed):
            self.do_partial_pipeline()

    def test_refresh_token(self) -> None:
        self.strategy.set_settings({"SOCIAL_AUTH_GITHUB_TEAM_ID": "123"})
        with self.assertRaises(AuthFailed):
            self.do_refresh_token()
