import abc
from typing import List, Dict

WS_AUTH_STRAT = "kbaseworkspace"


class AuthStrategy(abc.ABC):
    """
    An AuthStrategy is a class that determines how to judge whether a user has access to view/write to
    a job.

    Note that this is intended only for users - admins can do most things with jobs and don't go
    through the authstrategy to figure that out.
    """

    @abc.abstractmethod
    def can_read(self, auth_param: str) -> bool:
        """
        Given some auth param for the strategy, should return whether a user can read a job
        associated with it.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def can_read_list(self, auth_params: List[str]) -> Dict[str, bool]:
        """
        Given a list of auth params for this strategy, this returns a dictionary (auth_param -> bool)
        of whether a user can read jobs associated with each auth param.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def can_write(self, auth_param: str) -> bool:
        """
        From some auth param for this strategy, return whether a user can write job information
        associated with it.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def can_write_list(self, auth_params: List[str]) -> Dict[str, bool]:
        """
        From a list of auth_params for this strategy, return a dictionary (auth_param -> bool)
        of whether a user can write jobs associated with each auth param.
        """
        raise NotImplementedError()
