from typing import List, Dict
from enum import Enum
from lib.execution_engine2.authorization.basestrategy import AuthStrategy
from lib.installed_clients.WorkspaceClient import Workspace
from lib.installed_clients.baseclient import ServerError

STRATEGY = "kbaseworkspace"


class WorkspacePermission(Enum):
    ADMINISTRATOR = "a"
    READ_WRITE = "w"
    READ = "r"
    NONE = "n"


class WorkspaceAuth(AuthStrategy):
    def __init__(self, token: str, user_id: str, ws_url: str):
        self.ws_client = Workspace(url=ws_url, token=token)
        self.user_id = user_id

    def can_read(self, auth_param: str) -> bool:
        """
        Returns whether a user can read the workspace given in the auth_param.
        :param auth_param: a workspace id
        :returns: bool - True if the user can read
        """
        perms = self._get_workspace_permissions([auth_param])
        return self._has_read_perm(perms.get(auth_param, WorkspacePermission.NONE))

    def can_write(self, auth_param: str) -> bool:
        """
        Returns whether a user can write to the workspace given in the auth param.
        :param auth_param: a workspace id
        :returns: bool - True if the user can write
        """
        perms = self._get_workspace_permissions([auth_param])
        return self._has_write_perm(perms.get(auth_param, WorkspacePermission.NONE))

    def can_read_list(self, auth_params: List[str]) -> Dict[str, bool]:
        """
        Returns whether a user can read any of the workspaces given by the auth params.
        :param auth_params: a list of workspace ids
        :returns: dict[str, bool] - keys are the workspace ids, and the values are True if
                  the user can read
        """
        perms = self._get_workspace_permissions(auth_params)
        ret_perms = dict()
        for p in auth_params:
            ret_perms[p] = self._has_read_perm(perms.get(p, WorkspacePermission.NONE))
        return ret_perms

    def can_write_list(self, auth_params: List[str]) -> Dict[str, bool]:
        """
        Returns whether a user can write to any of the workspaces given by the auth params.
        :param auth_params: a list of workspace ids
        :returns: dict[str, bool] - keys are the workspace ids, and the values are True if
                  the user can write
        """
        perms = self._get_workspace_permissions(auth_params)
        ret_perms = dict()
        for p in auth_params:
            ret_perms[p] = self._has_write_perm(perms.get(p, WorkspacePermission.NONE))
        return ret_perms

    def _has_read_perm(self, perm: WorkspacePermission) -> bool:
        """
        Returns True if the given perm represents a permission with a minimum read level.
        :param perm: a WorkspacePermission
        :returns: a boolean - True if the perm is at least read.
        """
        read_perms = [
            WorkspacePermission.ADMINISTRATOR,
            WorkspacePermission.READ_WRITE,
            WorkspacePermission.READ,
        ]
        return perm in read_perms

    def _has_write_perm(self, perm: WorkspacePermission) -> bool:
        """
        Returns True if the given perm represents a permission with a minimum write level.
        :param perm: a WorkspacePermission
        :returns: a boolean - True if the perm is write or admin.
        """
        write_permissions = [
            WorkspacePermission.ADMINISTRATOR,
            WorkspacePermission.READ_WRITE,
        ]
        return perm in write_permissions

    def _get_workspace_permissions(
        self, ws_ids: List[str]
    ) -> Dict[str, WorkspacePermission]:
        """
        Fetches workspaces by id (expects a string, but an int should be ok), and
        returns user permissions as a dictionary. Keys are the workspace ids, and permissions
        are the user's WorkspacePermission for that workspace.

        If any workspace is deleted, or any other Workspace error happens, this raises a
        RuntimeError.
        """
        params = [{"id": w} for w in ws_ids]
        try:
            perm_list = self.ws_client.get_permissions_mass({"workspaces": params})[
                "perms"
            ]
        except ServerError as e:
            raise RuntimeError(
                "An error occurred while fetching user permissions from the Workspace",
                e,
            )

        perms = dict()
        for idx, ws_id in enumerate(ws_ids):
            perm = WorkspacePermission.NONE
            cur_ws_perm = perm_list[idx]
            if self.user_id in cur_ws_perm:
                perm = WorkspacePermission(cur_ws_perm[self.user_id])
            if "*" in cur_ws_perm and perm == WorkspacePermission.NONE:
                perm = WorkspacePermission(cur_ws_perm["*"])
            perms[ws_id] = perm
        return perms
