class DeployException(Exception):
    pass


class BuildFailed(DeployException):
    pass


class RunFailed(DeployException):
    pass


class DeployCancelled(DeployException):
    pass
