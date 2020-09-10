from abc import ABC, abstractmethod


class Scheduler(ABC):
    @abstractmethod
    def run_job(self, params, submit_file=None):
        raise NotImplementedError

    @abstractmethod
    def create_submit(self, params):
        raise NotImplementedError

    def validate_submit_file(self,):
        raise NotImplementedError

    @abstractmethod
    def run_submit(self, submit):
        raise NotImplementedError

    @abstractmethod
    def get_job_info(self, job_id, cluster_id):
        raise NotImplementedError

    @abstractmethod
    def get_user_info(self, user_id, projection=None):
        raise NotImplementedError

    @abstractmethod
    def cancel_job(self, job_id):
        raise NotImplementedError
