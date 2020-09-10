"""
A utility class for fetching roles for a token and caching them.
This makes use of the TokenCache in the built-in service auth client.

This is an SDK-based service, so auth token validation is handled through
the Server. This just takes an auth token and discerns whether there's
a valid EE2 admin role attached to the user.
"""
from json import JSONDecodeError
from typing import List, Set, Optional

import requests

from lib.execution_engine2.exceptions import AuthError
from lib.installed_clients.authclient import TokenCache

IS_ADMIN = "EE2_ADMIN"
NOT_ADMIN = "NOT_ADMIN"

_admin_cache = TokenCache()


class AdminAuthUtil:
    """
    A simple Auth utility. This is NOT an auth client, but a utility class that's
    used to look up user roles.
    """

    def __init__(self, auth_url: str, admin_roles: List):
        """
        :param auth_url: string - the base url of the KBase auth2 service.
        :param admin_roles: List - a list of roles that are allowed to be EE2 admins
        """
        # Use the token cache from the service's authclient, but put in strings for whether the
        # token's account is an admin or not.
        self.auth_url = auth_url
        self.admin_roles = set(admin_roles)

    def is_admin(self, token: str) -> bool:
        """
        Fetches the admin role information from the cache, or from the auth server.
        will raise a ValueError if:
          * token is None
        will raise an AuthError if:
          * token is invalid (401 from auth server)
        will raise a RuntimeError if:
          * any other auth server error
          * auth service times out
        :param token: an auth Token
        :return: boolean - True if the user has EE2 admin privs, False otherwise.
        """
        if not token:
            raise ValueError("Must supply token to check privileges")
        is_admin = _admin_cache.get_user(token)
        # is_admin will be a string if present, either IS_ADMIN or NOT_ADMIN
        if is_admin is not None:
            return is_admin == IS_ADMIN

        # if we don't have the info, go fetch it
        roles = self._fetch_user_roles(token)
        if self.admin_roles.intersection(set(roles)):
            _admin_cache.add_valid_token(token, IS_ADMIN)
            return True
        else:
            _admin_cache.add_valid_token(token, NOT_ADMIN)
            return False

    def get_admin_role(self, token: str, read_role, write_role) -> Optional[str]:
        roles = self._fetch_user_roles(token)
        if write_role in roles:
            return write_role
        if read_role in roles:
            return read_role
        return None

    def get_user_roles(self, token: str) -> List:
        return list(self._fetch_user_roles(token=token))

    def _fetch_user_roles(self, token: str) -> Set:
        """
        Returns the user's custom roles from the auth server as a Set.
        :param token: the Auth token
        :returns: Set - the set of customroles assigned to the user
        """
        if not token:
            raise ValueError("Must supply a token to fetch user roles")
        try:
            ret = requests.get(
                self.auth_url + "/api/V2/me", headers={"Authorization": token}
            )
            ret.raise_for_status()  # this is a no-op if all is well
            user_info = ret.json()
            return set(user_info.get("customroles", []))
        except requests.HTTPError as e:
            err_msg = dict()
            try:
                err_msg = e.response.json().get("error", {})
            except JSONDecodeError:
                pass
            if e.response.status_code == 401:
                raise AuthError("Token is not valid")
            raise RuntimeError(
                "An error occurred while fetching user roles from auth service: {} {}\n{}".format(
                    e.response.status_code,
                    e.response.reason,
                    err_msg.get("message", "Unknown Auth error"),
                )
            )
        except requests.exceptions.ConnectTimeout:
            raise RuntimeError("The auth service timed out while fetching user roles.")
