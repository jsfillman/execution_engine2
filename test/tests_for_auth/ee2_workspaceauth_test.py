import unittest
import requests_mock
import os
from configparser import ConfigParser
from execution_engine2.authorization.workspaceauth import WorkspaceAuth


class WorkspaceAuthTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.user = "some_user"
        config_file = os.environ.get("KB_DEPLOYMENT_CONFIG", "test/deploy.cfg")
        cls.cfg = dict()
        config = ConfigParser()
        config.read(config_file)
        for nameval in config.items("execution_engine2"):
            cls.cfg[nameval[0]] = nameval[1]
        cls.ws_url = cls.cfg["workspace-url"]

    def _mock_ok_ws_perms(self, rq_mock, user_id, ws_id_map):
        """
        :param ws_id_map: dict where key = workspace id, value = workspace permission
        """
        perm_response = [{user_id: ws_id_map[ws_id]} for ws_id in ws_id_map]
        ws_response = {"result": [{"perms": perm_response}], "version": "1.1"}
        rq_mock.register_uri("POST", self.ws_url, json=ws_response)

    def _mock_ws_deleted(self, rq_mock, ws_id):
        response = {
            "error": {
                "code": -32500,
                "error": "An error occurred!",
                "message": f"Workspace {ws_id} is deleted",
                "name": "JSONRpcError",
            },
            "version": "1.1",
        }
        rq_mock.register_uri(
            "POST", self.ws_url, [{"json": response, "status_code": 500}]
        )

    @requests_mock.Mocker()
    def test_can_read_ok(self, rq_mock):
        cases = {"123": True, "456": True, "789": False, "321": True}
        ws_id_map = {"123": "r", "456": "a", "789": "n", "321": "w"}
        for ws_id in ws_id_map.keys():
            self._mock_ok_ws_perms(rq_mock, self.user, {ws_id: ws_id_map[ws_id]})
            wsauth = WorkspaceAuth("foo", self.user, self.ws_url)
            perms = wsauth.can_read(ws_id)
            self.assertEqual(perms, cases[ws_id])

    @requests_mock.Mocker()
    def test_can_read_fail(self, rq_mock):
        ws_id = 67890
        self._mock_ws_deleted(rq_mock, ws_id)
        with self.assertRaises(RuntimeError) as e:
            wsauth = WorkspaceAuth("foo", self.user, self.ws_url)
            wsauth.can_read(ws_id)
        self.assertIn(
            "An error occurred while fetching user permissions from the Workspace",
            str(e.exception),
        )

    @requests_mock.Mocker()
    def test_can_write_ok(self, rq_mock):
        cases = {"123": False, "456": True, "789": False, "321": True}
        ws_id_map = {"123": "r", "456": "a", "789": "n", "321": "w"}
        for ws_id in ws_id_map.keys():
            self._mock_ok_ws_perms(rq_mock, self.user, {ws_id: ws_id_map[ws_id]})
            wsauth = WorkspaceAuth("foo", self.user, self.ws_url)
            perms = wsauth.can_write(ws_id)
            self.assertEqual(perms, cases[ws_id])

    @requests_mock.Mocker()
    def test_can_write_fail(self, rq_mock):
        ws_id = 67890
        self._mock_ws_deleted(rq_mock, ws_id)
        with self.assertRaises(RuntimeError) as e:
            wsauth = WorkspaceAuth("foo", self.user, self.ws_url)
            wsauth.can_write(ws_id)
        self.assertIn(
            "An error occurred while fetching user permissions from the Workspace",
            str(e.exception),
        )

    @requests_mock.Mocker()
    def test_can_read_list_ok(self, rq_mock):
        ws_id_map = {"123": "r", "456": "a", "789": "n", "321": "w"}
        cases = {"123": True, "456": True, "789": False, "321": True}
        self._mock_ok_ws_perms(rq_mock, self.user, ws_id_map)
        wsauth = WorkspaceAuth("foo", self.user, self.ws_url)
        perms = wsauth.can_read_list(list(ws_id_map.keys()))
        self.assertEqual(perms, cases)

    @requests_mock.Mocker()
    def test_can_read_list_fail(self, rq_mock):
        ws_id = 67890
        self._mock_ws_deleted(rq_mock, ws_id)
        with self.assertRaises(RuntimeError) as e:
            wsauth = WorkspaceAuth("foo", self.user, self.ws_url)
            wsauth.can_read_list([ws_id])
        self.assertIn(
            "An error occurred while fetching user permissions from the Workspace",
            str(e.exception),
        )

    @requests_mock.Mocker()
    def test_can_write_list_ok(self, rq_mock):
        ws_id_map = {"123": "r", "456": "a", "789": "n", "321": "w"}
        cases = {"123": False, "456": True, "789": False, "321": True}
        self._mock_ok_ws_perms(rq_mock, self.user, ws_id_map)
        wsauth = WorkspaceAuth("foo", self.user, self.ws_url)
        perms = wsauth.can_write_list(list(ws_id_map.keys()))
        self.assertEqual(perms, cases)

    @requests_mock.Mocker()
    def test_can_write_list_fail(self, rq_mock):
        ws_id = 67890
        self._mock_ws_deleted(rq_mock, ws_id)
        with self.assertRaises(RuntimeError) as e:
            wsauth = WorkspaceAuth("foo", self.user, self.ws_url)
            wsauth.can_write_list([ws_id])
        self.assertIn(
            "An error occurred while fetching user permissions from the Workspace",
            str(e.exception),
        )
