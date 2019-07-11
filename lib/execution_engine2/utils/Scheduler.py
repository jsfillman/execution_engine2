from abc import  ABCMeta, abstractmethod

class Scheduler():

    def run_job(self, params, config):
        filepath = self.create_submit_file()
        self.cleanup_submit_file()
        job_id = self.run_submit_file(filepath)
        return job_id

    @abstractmethod
    def cleanup_submit_file(self,submit_filepath):
        raise NotImplementedError

    @abstractmethod
    def create_submit_file(self, params, config):
        raise NotImplementedError

    @abstractmethod
    def validate_submit_file(self, ):
        raise NotImplementedError

    @abstractmethod
    def run_submit_file(self, submit_filepath):
        raise NotImplementedError

    @abstractmethod
    def get_job_info(self, job_id, projection=None):
        raise NotImplementedError

    @abstractmethod
    def get_user_info(self, user_id, projection=None):
        raise NotImplementedError

    @abstractmethod
    def cancel_job(self, job_id):
        raise NotImplementedError
