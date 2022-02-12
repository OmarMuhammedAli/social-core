"""
Syrian Doctors OAuth2 backend
Reference for implementation: 
https://python-social-auth.readthedocs.io/en/latest/backends/implementation.html
"""

from .oauth import BaseOAuth2

class SyrianDoctorsOAuth2(BaseOAuth2):
    """Syrian Doctors authenticatoin backend"""
    name = 'syrian-doctors'
    AUTHORIZATION_URL = ''
    ACCESS_TOKEN_URL = ''
    ACCESSS_TOKEN_METHOD = 'POST'
    SCOPE_PARAMETER_NAME = 'scope'
    SCOPE_SEPARATOR = ' '

    def get_user_details(self, response):
        """Return user details from Syrian Doctors account"""
        return {
            'username': response.get('username'),
            'email': response.get('email'),
            'first_name': response.get('first_name'),
            'last_name': response.get('last_name'),
            'full_name': response.get('full_name'),
        }
    
    def user_data(self, access_token, *args, **kwargs):
        """Loads user data from service"""
        return self.get_json(
            'https://api.doctors.sy/v1/me',
            headers={'Authorization': 'Bearer {}'.format(access_token)}
        )

