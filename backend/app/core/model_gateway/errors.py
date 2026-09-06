from app.core.errors import MRPLAPIException

class ModelGatewayError(MRPLAPIException):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__("MODEL_GATEWAY_ERROR", message, status_code)

class ProviderConnectionError(ModelGatewayError):
    def __init__(self, provider: str, details: str):
        super().__init__(f"Failed to connect to provider '{provider}': {details}", 502)

class ProviderTimeoutError(ModelGatewayError):
    def __init__(self, provider: str):
        super().__init__(f"Request to provider '{provider}' timed out", 504)

class ModelNotFoundError(ModelGatewayError):
    def __init__(self, model: str):
        super().__init__(f"Model '{model}' not found or not supported", 404)

class UnsupportedCapabilityError(ModelGatewayError):
    def __init__(self, model: str, capability: str):
        super().__init__(f"Model '{model}' does not support capability: {capability}", 400)
