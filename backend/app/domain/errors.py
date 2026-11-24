class IntegrationError(Exception):
    """Base para errores que pueden traducirse de forma segura a HTTP."""


class InvalidUpload(IntegrationError):
    pass


class AuthenticationFailed(IntegrationError):
    pass


class ConfigurationError(IntegrationError):
    pass


class JobNotFound(IntegrationError):
    pass


class ResultNotReady(IntegrationError):
    pass


class StaleTransition(IntegrationError):
    pass


class StorageCleanupFailed(IntegrationError):
    pass


class ReadinessFailed(IntegrationError):
    pass
