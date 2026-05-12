import io
from typing import Any
from typing import Tuple

from ML_fasalX.core.exceptions import InvalidImageError

try:
    from PIL import Image, UnidentifiedImageError

    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover - covered in deployment checks
    Image = None
    UnidentifiedImageError = Exception
    PIL_AVAILABLE = False


def _get_lanczos():
    if hasattr(Image, "Resampling"):
        return Image.Resampling.LANCZOS
    return Image.LANCZOS


def preprocess_image(
    image_bytes: bytes,
    img_size: Tuple[int, int] = (224, 224),
    raw_input: bool = True,
) -> Any:
    if not PIL_AVAILABLE:
        raise InvalidImageError("Pillow is not installed in the ML runtime.")

    import numpy as np

    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.verify()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError("Uploaded file is not a valid image.") from exc

    image = image.resize(img_size, _get_lanczos())
    array = np.asarray(image, dtype=np.float32)

    if not raw_input:
        array = array / 255.0

    return np.expand_dims(array, axis=0)
