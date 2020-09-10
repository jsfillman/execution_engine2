from enum import Enum

from cachetools import TTLCache

from lib.execution_engine2.authorization.authstrategy import can_read_job, can_write_job
from lib.execution_engine2.authorization.roles import AdminAuthUtil
from lib.execution_engine2.db.models.models import Job


class JobPermissions(Enum):
    READ = "r"
    WRITE = "w"
    NONE = "n"


class AdminPermissions(Enum):
    READ = "r"
    WRITE = "w"
    NONE = "n"


class EE2Auth:
    def __init__(self, sdkmr):
        self.sdkmr = sdkmr

    @staticmethod
    def get_cache(cache, size, expire):
        if cache is None:
            cache = TTLCache(maxsize=size, ttl=expire)
        return cache

    def _lookup_admin_permissions(self):
        aau = AdminAuthUtil(self.sdkmr.auth_url, self.sdkmr.admin_roles)
        p = aau.get_admin_role(
            token=self.sdkmr.token,
            read_role=self.sdkmr.ADMIN_READ_ROLE,
            write_role=self.sdkmr.ADMIN_WRITE_ROLE,
        )
        if p == self.sdkmr.ADMIN_READ_ROLE:
            return AdminPermissions.READ
        elif p == self.sdkmr.ADMIN_WRITE_ROLE:
            return AdminPermissions.WRITE
        else:
            return AdminPermissions.NONE

    def _get_user_admin_permissions(self):
        if self.sdkmr.user_id not in self.sdkmr.admin_permissions_cache:
            self.sdkmr.admin_permissions_cache[
                self.sdkmr.user_id
            ] = self._lookup_admin_permissions()

        return self.sdkmr.admin_permissions_cache[self.sdkmr.user_id]

    def retrieve_admin_permissions(self):
        return {"permission": self._get_user_admin_permissions().value}

    def check_admin_permission(self, requested_perm):
        requested_perm = AdminPermissions(requested_perm.value)
        if requested_perm is AdminPermissions.NONE:
            raise PermissionError(
                "Permission Denied. You cannot request NONE admin permissions"
            )

        user_permission = self._get_user_admin_permissions()

        self.sdkmr.logger.debug(f"Requesting perm {requested_perm}, {user_permission}")
        if requested_perm == AdminPermissions.WRITE:
            if user_permission == AdminPermissions.WRITE:
                return True
            elif user_permission == AdminPermissions.READ:
                raise PermissionError(
                    "Access Denied: You are a read-only admin. This function requires write access"
                )
            else:
                raise PermissionError(
                    f"Access Denied: You are not an administrator. {user_permission}"
                )

        elif requested_perm == AdminPermissions.READ:
            if user_permission != AdminPermissions.NONE:
                return True
            else:
                raise PermissionError("Access Denied: You are not an administrator")
        else:
            raise PermissionError(
                "You didn't supply the correct job permissions types: READ or WRITE"
            )

    def get_job_permission_from_cache(self, job_id, level):
        """
        Permission[job_id][user_id][level]
        :param job_id:
        :param level:
        :return:
        """
        if not self.sdkmr.job_permission_cache.get(job_id):
            return False
        else:
            job_permission = self.sdkmr.job_permission_cache[job_id]
            if not job_permission.get(self.sdkmr.user_id):
                return False
            else:
                return job_permission[self.sdkmr.user_id].get(level)

    def _test_job_permission_with_cache(self, job_id, permission):
        if not self.get_job_permission_from_cache(job_id, permission):
            job = self.sdkmr.get_mongo_util().get_job(job_id=job_id)
            self.test_job_permissions(job, job_id, permission)
        self.sdkmr.logger.debug(
            "you have permission to {} job {}".format(permission, job_id)
        )

    def _update_job_permission_cache(self, job_id, user_id, level, perm):
        if not self.sdkmr.job_permission_cache.get(job_id):
            self.sdkmr.job_permission_cache[job_id] = {user_id: {level: perm}}
        else:
            job_permission = self.sdkmr.job_permission_cache[job_id]
            if not job_permission.get(user_id):
                job_permission[user_id] = {level: perm}
            else:
                job_permission[user_id][level] = perm

    def test_job_permissions(
        self, job: Job, job_id: str, level: JobPermissions
    ) -> bool:
        """
        Tests if the currently loaded token has the requested permissions for the given job.
        Returns True if so. Raises a PermissionError if not.
        Can also raise a RuntimeError if anything bad happens while looking up rights. This
        can be triggered from either Auth or Workspace errors.

        Effectively, this can be used the following way:
        some_job = get_job(job_id)
        _test_job_permissions(some_job, job_id, JobPermissions.READ)

        ...and continue on with code. If the user doesn't have permission, a PermissionError gets
        thrown. This can either be captured by the calling function, or allowed to propagate out
        to the user and just end the RPC call.

        :param job: a Job object to seek permissions for
        :param job_id: string - the id associated with the Job object
        :param level: string - the level to seek - either READ or WRITE
        :returns: True if the user has permission, raises a PermissionError otherwise.
        """
        # Remove this becase we don't want to do this unless we explicitly set the request to is_admin and as_admin
        # if sdkmr.is_admin:  # bypass if we're in admin mode.
        #     _update_job_permission_cache(sdkmr, job_id, sdkmr.user_id, level, True)
        #     return True
        perm = False
        try:
            if level.value == JobPermissions.READ.value:
                perm = can_read_job(
                    job, self.sdkmr.user_id, self.sdkmr.token, self.sdkmr.config
                )
                self._update_job_permission_cache(
                    job_id, self.sdkmr.user_id, level, perm
                )
            elif level.value == JobPermissions.WRITE.value:
                perm = can_write_job(
                    job, self.sdkmr.user_id, self.sdkmr.token, self.sdkmr.config
                )
                self._update_job_permission_cache(
                    job_id, self.sdkmr.user_id, level, perm
                )
            else:
                raise PermissionError(
                    f"Please provide a valid level of permissions  {level}"
                )
            if not perm:
                raise PermissionError(
                    f"User {self.sdkmr.user_id} does not have permission to {level} job {job_id}"
                )
        except RuntimeError as e:
            self.sdkmr.logging.error(
                f"An error occurred while checking permissions for job {job_id}"
            )
            raise e
        return perm


#
# def check_admin_permission(requested_perm, user_id, admin_cache, auth_url, auth_roles):
#     if user_id not in admin_cache:
#         admin_cache[user_id] = lookup_admin_permissions(auth_url,auth_roles,token)
#
#     user_permission = admin_cache[user_id]
#     requested_perm = AdminPermissions(requested_perm)
#
#     if requested_perm == AdminPermissions.WRITE:
#         if user_permission == AdminPermissions.WRITE:
#             return True
#         elif user_permission == AdminPermissions.READ:
#             raise PermissionError(
#                 "Access Denied: You are a read-only admin. This function requires write access")
#         else:
#             raise PermissionError("Access Denied: You are not an administrator.")
#
#     elif requested_perm == AdminPermissions.READ:
#         if user_permission != AdminPermissions.NONE:
#             return True
#         else:
#             raise PermissionError("Access Denied: You are not an administrator")
#     else:
#         raise Exception(
#             "Programming Error: You didn't supply the correct job permissions types")


# def admin_permissions(*outer_args, **outer_kwargs):
#     def decorator(func):
#         def decorated(*args, **kwargs):
#             as_admin = kwargs.get("as_admin", False)
#             if as_admin:
#                 perm = outer_kwargs['permission']
#                 admin_cache = outer_kwargs['admin_cache']
#                 user_id = outer_kwargs['user_id']
#                 check_admin_permission(user_id=user_id, permission=perm, admin_cache=admin_cache)
#             return (func(*args, **kwargs))
#         return decorated
#     return decorator

# def admin_permissions(user_id, admin_cache, requested_perm):
#     def decorator(func):
#         def decorated(*args, **kwargs):
#             as_admin = kwargs.get("as_admin", False)
#             if as_admin:
#                 check_admin_permission(user_id=user_id, requested_perm=requested_perm, admin_cache=admin_cache)
#             return (func(*args, **kwargs))
#         return decorated
#     return decorator
#
#


# def as_admin_write(func):
#     def func_wrapper(self, *args, **kwargs):
#         as_admin = kwargs.get("as_admin", False)
#         if as_admin:
#             check_admin_permission(permission=JobPermissions.WRITE)
#         return (func(*args, **kwargs))
#
#     return func_wrapper

#
# def get_roles(sdklmr, user_id, token):
#     if user_id in sdkmr.roles_cache:
#         roles = sdkmr.roles_cache.get(user_id)
#     else:
#         aau = AdminAuthUtil(sdkmr.auth_url, sdkmr.admin_roles)
#         roles = aau.get_user_roles()
#         sdkmr.roles_cache[user_id] = roles
#     return roles
