from __future__ import annotations


class VisionServiceError(RuntimeError):
    code = "vision_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.user_message = message


class VisionProviderUnavailableError(VisionServiceError):
    code = "vision_provider_unavailable"


class UnsupportedMultimodalProviderError(VisionServiceError):
    code = "unsupported_multimodal_provider"


class InvalidVisionInputError(VisionServiceError):
    code = "invalid_vision_input"


class RemoteVisionProviderError(VisionServiceError):
    code = "remote_vision_provider_error"
