import slack


class SlackClient:
    def __init__(
        self,
        token,
        channel="#execution_engine_notifications",
        debug=False,
        endpoint=None,
    ):
        if token is None:
            raise Exception("Please set add slack token to deploy.cfg")
        self.client = slack.WebClient(token=token)
        self.channel = channel
        self.debug = debug
        self.endpoint = endpoint or "Endpoint not set"

    def held_job_message(self, held_job):
        message = f"Held Job Stats {held_job}"
        self.client.chat_postMessage(channel=self.channel, text=message)

    def ee2_reaper_failure(self, endpoint="Unknown EE2 URL", job_id="Unknown"):
        message = f"EE2 Held Job reaper failed for {endpoint}  (job {job_id}). Please check it out"
        self.client.chat_postMessage(channel=self.channel, text=message)

    def ee2_reaper_success(
        self,
        job_id,
        batch_name,
        calculated_hold_reason,
        status,
        hold_reason_code,
        hold_reason,
    ):
        if not calculated_hold_reason:
            calculated_hold_reason = "Unknown"
        message = f"Job {job_id} {batch_name } was successfully marked as error (status == {status}). It probably died because of {calculated_hold_reason} ({hold_reason} {hold_reason_code}"
        self.client.chat_postMessage(channel=self.channel, text=message)

    def run_job_message(self, job_id, scheduler_id, username):
        if self.debug is False:
            return

        message = f"{username} has submitted job_id:{job_id} scheduler_id:{scheduler_id} ({self.endpoint}) "
        self.client.chat_postMessage(channel=self.channel, text=message)

    def cancel_job_message(self, job_id, scheduler_id, termination_code):
        if self.debug is False:
            return

        message = f"scheduler_id:{scheduler_id} job_id:{job_id} has been canceled due to {termination_code} ({self.endpoint})"
        self.client.chat_postMessage(channel=self.channel, text=message)

    def finish_job_message(self, job_id, scheduler_id, finish_status, error_code=None):
        if self.debug is False:
            return

        message = f"scheduler_id:{scheduler_id} job_id:{job_id} has ended with a status of {finish_status} ({self.endpoint})"
        if error_code is not None:
            message += f" Error code is {error_code}"
        self.client.chat_postMessage(channel=self.channel, text=message)
