import json
from typing import List, Dict

from lib.installed_clients.CatalogClient import Catalog


class CatalogUtils:
    def __init__(self, url, admin_token):
        self.catalog = Catalog(url=url, token=admin_token)

    def get_normalized_resources(self, method) -> Dict:
        """
        get client groups info from Catalog
        """
        if method is None:
            raise ValueError("Please input module_name.function_name")

        if method is not None and "." not in method:
            raise ValueError(
                "unrecognized method: {}. Please input module_name.function_name".format(
                    method
                )
            )

        module_name, function_name = method.split(".")

        group_config = self.catalog.list_client_group_configs(
            {"module_name": module_name, "function_name": function_name}
        )

        job_settings = []
        if group_config and len(group_config) > 0:
            job_settings = group_config[0].get("client_groups")

        normalize = self.normalize_job_settings(job_settings)

        return normalize

    @staticmethod
    def normalize_job_settings(resources_request: List):
        """
        Ensure that the client_groups are processed as a dictionary and has at least one value
        :param resources_request: either an empty string, a json object, or cg,key1=value,key2=value
        :return:
        """

        # No client group provided
        if len(resources_request) == 0:
            return {}
        # JSON
        if "{" in resources_request[0]:
            json_resources_request = ", ".join(resources_request)
            return json.loads(json_resources_request)
        # CSV Format
        rr = resources_request[0].split(",")  # type: list
        rv = {"client_group": rr.pop(0)}
        for item in rr:
            if "=" not in item:
                raise Exception(
                    f"Malformed requirement. Format is <key>=<value> . Item is {item}"
                )
            (key, value) = item.split("=")
            rv[key] = value
        #
        # print("Going to return", rv)
        return rv
