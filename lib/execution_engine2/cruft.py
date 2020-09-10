# # def _run_admin_command(self, command, params):
# #     available_commands = ["cancel_job", "view_job_logs"]
# #     if command not in available_commands:
# #         raise ValueError(f"{command} not an admin command. See {available_commands} ")
# #     commands = {"cancel_job": self.cancel_job, "view_job_logs": self.view_job_logs}
# #     p = {
# #         "cancel_job": {
# #             "job_id": params.get("job_id"),
# #             "terminated_code": params.get(
# #                 "terminated_code", TerminatedCode.terminated_by_admin.value
# #             ),
# #         },
# #         "view_job_logs": {"job_id": params.get("job_id")},
# #     }
# #     return commands[command](**p[command])
# #
# #     def admin_role(self, token):
# #         """
# #         Check to see which role the given token has
# #         :param token: Token to inspect
# #         :return: One of 'EE2_ADMIN_RO' or 'EE2_ADMIN` or None
# #         """
# #         return AdminAuthUtil(self.auth_url, self.admin_roles).get_admin_role(
# #             token=token, read_role="EE2_ADMIN_RO", write_role="EE2_ADMIN"
# #         )
# #
# #     def get_job_wrapper(self, job_id, required_admin_role=None):
# #         """
# #         If you are an admin, you can
# #         If you are not an admin, you
# #         :param job_id:
# #         :return:
# #         """
# #         if required_admin_role is not None and required_admin_role in self.roles:
# #             job = self.get_mongo_util().get_job(job_id=job_id)
# #             logging.info(f"ADMIN USER has permission to cancel job {job_id}")
# #             self.logger.debug(f"ADMIN USER has permission to cancel job {job_id}")
# #         else:
# #             job = self.get_job_with_permission(job_id, JobPermissions.WRITE)
# #             logging.info(f"User has permission to cancel job {job_id}")
# #             self.logger.debug(f"User has permission to cancel job {job_id}")
# #         return job
# #
# #     def administer(self, command, params, token):
# #         """
# #         Run commands as an administrator. Requires a token for a user with an EE2 administrative role.
# #         Currently allowed commands are cancel_job and view_job_logs.
# #
# #         Commands are given as strings, and their parameters are given as a dictionary of keys and values.
# #         For example:
# #             administer("cancel_job", {"job_id": 12345}, auth_token)
# #         is the same as running
# #             cancel_job(12345)
# #         but with administrative privileges.
# #         :param command: The command to run (See specfile)
# #         :param params: The parameters for that command that will be expanded (See specfile)
# #         :param token: The auth token (Will be checked for the correct auth role)
# #         :return:
# #         """
# #         logging.info(
# #             f'Attempting to run administrative command "{command}" as user {self.user_id}'
# #         )
# #         # set admin privs, one way or the other
# #         self.is_admin = self._is_admin(token)
# #         if not self.is_admin:
# #             raise PermissionError(
# #                 f"User {self.user_id} is not authorized to run administrative commands."
# #             )
# #         self._run_admin_command(command, params)
# #         self.is_admin = False
#
#
# def process_old_format(self, cg_resources_requirements):
#     """
#     Old format is njs,request_cpu=1,request_memory=1,request_disk=1,request_color=blue
#     Regex is assumed to be true
#
#     :param cg_resources_requirements:
#     :return:
#     """
#     cg_res_req_split = cg_resources_requirements.split(",")  # List
#
#     # Access and remove clientgroup from the statement
#     client_group = cg_res_req_split.pop(0)
#
#     requirements = dict()
#     for item in cg_res_req_split:
#         (req, value) = item.split("=")
#         requirements[req] = value
#
#     # Set up default resources
#     resources = self.get_default_resources(client_group)
#
#     if client_group is None or client_group is "":
#         client_group = resources[self.CG]
#
#     requirements_statement = []
#
#     for key, value in requirements.items():
#         if key in resources:
#             # Overwrite the resources with catalog entries
#             resources[key] = value
#         else:
#             # Otherwise add it to the requirements statement
#             requirements_statement.append(f"{key}={value}")
#
#     # Delete special keys
#     print(resources)
#     print(requirements)
#
#     del requirements[self.REQUEST_MEMORY]
#     del requirements[self.REQUEST_CPUS]
#     del requirements[self.REQUEST_DISK]
#
#     # Set the clientgroup just in case it was blank
#
#     # Add clientgroup to resources because it is special
#     # Regex is enabled by default
#     cge = f'regexp("{client_group}",CLIENTGROUP)'
#     requirements_statement.append(cge)
#
#     rv = dict()
#     rv[self.CG] = client_group
#     rv["client_group_expression"] = cge
#     rv["requirements"] = "".join(requirements_statement)
#     rv["requirements_statement"] = cge
#     for key, value in resources.items():
#         rv[key] = value
#
#     return rv
#
#
# def process_new_format(self, client_group_and_requirements):
#     """
#     New format is {'client_group' : 'njs', 'request_cpu' : 1, 'request_disk' :
#     :param client_group_and_requirements:
#     :return:
#     """
#     reqs = json.loads(client_group_and_requirements)
#
#     def generate_requirements(self, cg_resources_requirements):
#         print(cg_resources_requirements)
#         if "{" in cg_resources_requirements:
#             reqs = self.process_new_format(cg_resources_requirements)
#         else:
#             reqs = self.process_old_format(cg_resources_requirements)
#
#         self.check_for_missing_requirements(reqs)
#
#         return self.resource_requirements(
#             request_cpus=reqs["request_cpus"],
#             request_disk=reqs["request_disk"],
#             request_memory=reqs["request_memory"],
#             requirements_statement=reqs["requirements"],
#         )
#         return r
#
#     @staticmethod
#     def check_for_missing_requirements(requirements):
#         for item in (
#             "client_group_expression",
#             "request_cpus",
#             "request_disk",
#             "request_memory",
#         ):
#             if item not in requirements:
#                 raise MissingCondorRequirementsException(
#                     f"{item} not found in requirements"
#                 )
#
#     def _process_requirements_new_format(self, requirements):
#         requirements = dict()
#         cg = requirements.get("client_group", "")
#         if cg is "":
#             # requirements[
#
#             if bool(requirements.get("regex", False)) is True:
#                 cg["client_group_requirement"] = f'regexp("{cg}",CLIENTGROUP)'
#             else:
#                 cg["client_group_requirement"] = f"+CLIENTGROUP == {client_group} "
