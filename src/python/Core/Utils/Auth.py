from typing import Union
from datetime import datetime, timedelta
import cernrequests

sso_token = None
sso_token_expiration = None
# How much time before the token expiration should
# we request a new one.
EXPIRATION_DEADLINE = timedelta(minutes=5)


def is_sso_token_still_valid(sso_token_expiration: Union[datetime, None]):
    if not sso_token_expiration:
        return False
    return (sso_token_expiration - datetime.now()) > EXPIRATION_DEADLINE


def get_cern_sso_api_token(
    client_id: Union[str, None],
    client_secret: Union[str, None],
    target_application: Union[str, None],
) -> Union[str, None]:
    global sso_token
    global sso_token_expiration
    if not client_id or not client_secret:
        raise Exception(
            "client_id and client_secret are both required to get an SSO token"
        )
    if not is_sso_token_still_valid(sso_token_expiration):
        sso_token, sso_token_expiration = cernrequests.get_api_token(
            client_id=client_id,
            client_secret=client_secret,
            target_application=target_application,
        )
    return sso_token
