class MLServiceError(Exception):
    def __init__(self, message: str, code: str = "ML_SERVICE_ERROR", status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class ModelNotFoundError(MLServiceError):
    def __init__(self, crop_name: str):
        super().__init__(
            message=f"No disease model and label file pair found for crop '{crop_name}'.",
            code="MODEL_NOT_FOUND",
            status_code=404,
        )


class ModelLoadError(MLServiceError):
    def __init__(self, crop_name: str, reason: str):
        super().__init__(
            message=f"Failed to load disease model for crop '{crop_name}': {reason}",
            code="MODEL_LOAD_ERROR",
            status_code=500,
        )


class InvalidImageError(MLServiceError):
    def __init__(self, reason: str = "Invalid image input."):
        super().__init__(
            message=reason,
            code="INVALID_IMAGE",
            status_code=400,
        )


class PredictionError(MLServiceError):
    def __init__(self, reason: str):
        super().__init__(
            message=f"Prediction failed: {reason}",
            code="PREDICTION_ERROR",
            status_code=500,
        )

