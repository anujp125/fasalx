import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ML_fasalX.core.config import Settings, settings
from ML_fasalX.core.exceptions import ModelLoadError, ModelNotFoundError

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

try:
    import tensorflow as tf
    from tensorflow.keras.models import load_model

    tf.get_logger().setLevel("ERROR")
    TF_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on runtime image
    tf = None
    load_model = None
    TF_AVAILABLE = False


logger = logging.getLogger(__name__)


CROP_ALIASES = {
    "soybean": "soyabeen",
    "blackgram": "blackgrams",
    "papaya": "Papaya",
}


@dataclass(frozen=True)
class ModelFiles:
    crop_name: str
    model_path: Path
    label_path: Path


@dataclass
class ModelArtifact:
    crop_name: str
    model_path: Path
    label_path: Path
    model: Any
    labels: list[str]
    raw_input: bool


class ModelRegistry:
    def __init__(self, config: Settings = settings):
        self.config = config
        self._lock = threading.RLock()
        self._file_index: dict[str, Path] | None = None
        self._available_models: list[ModelFiles] | None = None
        self._loaded_by_model_path: dict[str, ModelArtifact] = {}
        self._crop_to_model_key: dict[str, str] = {}

    def refresh(self) -> None:
        with self._lock:
            self._file_index = None
            self._available_models = None
            self._crop_to_model_key.clear()

    def list_available_models(self) -> list[dict[str, Any]]:
        with self._lock:
            models = self._discover_available_models()
            loaded_keys = set(self._loaded_by_model_path)
            return [
                {
                    "crop_name": model_files.crop_name,
                    "model_file": model_files.model_path.name,
                    "label_file": model_files.label_path.name,
                    "loaded": self._cache_key(model_files.model_path) in loaded_keys,
                }
                for model_files in models
            ]

    def load_crop_model(self, crop_name: str) -> ModelArtifact:
        if not TF_AVAILABLE:
            raise ModelLoadError(crop_name, "TensorFlow/Keras is not installed.")

        normalized_crop = self._normalize_crop_name(crop_name)
        if not normalized_crop:
            raise ModelLoadError(crop_name, "Crop name is required.")

        with self._lock:
            cached_model_key = self._crop_to_model_key.get(normalized_crop)
            if cached_model_key and cached_model_key in self._loaded_by_model_path:
                return self._loaded_by_model_path[cached_model_key]

            model_files = self._find_model_files(crop_name)
            if model_files is None:
                raise ModelNotFoundError(crop_name)

            model_key = self._cache_key(model_files.model_path)
            if model_key in self._loaded_by_model_path:
                artifact = self._loaded_by_model_path[model_key]
                self._crop_to_model_key[normalized_crop] = model_key
                return artifact

            try:
                model = load_model(model_files.model_path, compile=False)
                labels = self._load_labels(model_files.label_path)
                raw_input = self._has_builtin_preprocessing(model)
            except json.JSONDecodeError as exc:
                raise ModelLoadError(crop_name, f"Corrupted JSON label file: {exc}") from exc
            except OSError as exc:
                raise ModelLoadError(crop_name, f"Model or label file is unreadable: {exc}") from exc
            except Exception as exc:
                raise ModelLoadError(crop_name, str(exc)) from exc

            artifact = ModelArtifact(
                crop_name=model_files.crop_name,
                model_path=model_files.model_path,
                label_path=model_files.label_path,
                model=model,
                labels=labels,
                raw_input=raw_input,
            )
            self._loaded_by_model_path[model_key] = artifact
            self._crop_to_model_key[normalized_crop] = model_key

            logger.info(
                "loaded_crop_model",
                extra={
                    "crop_name": model_files.crop_name,
                    "model_file": model_files.model_path.name,
                    "label_file": model_files.label_path.name,
                    "class_count": len(labels),
                    "raw_input": raw_input,
                },
            )
            return artifact

    def warm_up(self, crop_names: list[str] | None = None, warm_all: bool = False) -> dict[str, Any]:
        target_crops = crop_names or []
        if warm_all:
            target_crops = [entry["crop_name"] for entry in self.list_available_models()]

        warmed: list[str] = []
        failed: dict[str, str] = {}

        for crop_name in target_crops:
            try:
                artifact = self.load_crop_model(crop_name)
                self._run_model_warmup_prediction(artifact)
                warmed.append(crop_name)
            except Exception as exc:
                failed[crop_name] = str(exc)
                logger.warning(
                    "model_warmup_failed",
                    extra={"crop_name": crop_name, "error": str(exc)},
                )

        return {"warmed": warmed, "failed": failed}

    def _file_map(self) -> dict[str, Path]:
        if self._file_index is not None:
            return self._file_index

        models_dir = self.config.MODELS_DIR
        if not models_dir.exists():
            self._file_index = {}
            return self._file_index

        self._file_index = {
            file_path.name.lower(): file_path
            for file_path in models_dir.iterdir()
            if file_path.is_file()
        }
        return self._file_index

    def _discover_available_models(self) -> list[ModelFiles]:
        if self._available_models is not None:
            return self._available_models

        file_map = self._file_map()
        model_paths = [
            path
            for name, path in file_map.items()
            if name.endswith((".keras", ".h5"))
        ]
        discovered: list[ModelFiles] = []

        for model_path in sorted(model_paths, key=lambda path: path.name.lower()):
            crop_name = self._crop_name_from_model_file(model_path.name)
            label_path = self._find_label_for_crop(crop_name, model_path)
            if label_path:
                discovered.append(
                    ModelFiles(
                        crop_name=crop_name,
                        model_path=model_path,
                        label_path=label_path,
                    )
                )

        self._available_models = discovered
        return discovered

    def _find_model_files(self, crop_name: str) -> ModelFiles | None:
        search_names = [crop_name]
        alias = CROP_ALIASES.get(crop_name.lower().strip())
        if alias:
            search_names.insert(0, alias)

        file_map = self._file_map()
        for search_name in search_names:
            for model_file, label_file in self._all_model_candidates(search_name):
                model_path = file_map.get(model_file.lower())
                label_path = file_map.get(label_file.lower())
                if model_path and label_path:
                    return ModelFiles(
                        crop_name=self._crop_name_from_model_file(model_path.name),
                        model_path=model_path,
                        label_path=label_path,
                    )

        for search_name in search_names:
            crop_token = self._compact(search_name)
            for file_name, model_path in file_map.items():
                if not file_name.endswith((".keras", ".h5")):
                    continue
                if crop_token not in self._compact(file_name):
                    continue

                crop_name_from_file = self._crop_name_from_model_file(model_path.name)
                label_path = self._find_label_for_crop(crop_name_from_file, model_path)
                if label_path:
                    return ModelFiles(
                        crop_name=crop_name_from_file,
                        model_path=model_path,
                        label_path=label_path,
                    )

        return None

    def _find_label_for_crop(self, crop_name: str, model_path: Path) -> Path | None:
        file_map = self._file_map()
        model_stem = model_path.stem.lower()
        crop_token = self._compact(crop_name)

        candidates = []
        for _, label_file in self._all_model_candidates(crop_name):
            candidates.append(label_file.lower())
        candidates.extend(
            [
                f"{model_stem}_classes.json",
                f"{model_stem}_labels.json",
                f"{model_stem}.json",
            ]
        )

        for candidate in candidates:
            if candidate in file_map:
                return file_map[candidate]

        for file_name, label_path in file_map.items():
            if file_name.endswith(".json") and crop_token in self._compact(file_name):
                return label_path

        return None

    @staticmethod
    def _all_model_candidates(crop_name: str) -> list[tuple[str, str]]:
        crop_name = crop_name.strip()
        base_variants = {
            crop_name,
            crop_name.lower(),
            crop_name.upper(),
            crop_name.title(),
            crop_name.lower().replace(" ", "_"),
            crop_name.lower().replace(" ", "-"),
            crop_name.lower().replace("_", ""),
            crop_name.replace(" ", ""),
        }
        model_suffixes = ["", "_disease", "_model", "_diseases", "_classifier", "_mobilenet_transfer"]
        label_suffixes = ["", "_labels", "_classes", "_disease_labels", "_disease_classes"]
        model_extensions = [".keras", ".h5"]
        label_extensions = [".json"]

        candidates: list[tuple[str, str]] = []
        for base in base_variants:
            for model_suffix in model_suffixes:
                for model_extension in model_extensions:
                    for label_suffix in label_suffixes:
                        for label_extension in label_extensions:
                            candidates.append(
                                (
                                    f"{base}{model_suffix}{model_extension}",
                                    f"{base}{label_suffix}{label_extension}",
                                )
                            )
        return candidates

    @staticmethod
    def _load_labels(label_path: Path) -> list[str]:
        with label_path.open("r", encoding="utf-8") as label_file:
            raw_labels = json.load(label_file)

        if isinstance(raw_labels, list):
            return [str(label) for label in raw_labels]

        if isinstance(raw_labels, dict):
            if all(str(index) in raw_labels for index in range(len(raw_labels))):
                return [str(raw_labels[str(index)]) for index in range(len(raw_labels))]

            try:
                return [
                    str(label)
                    for label, _ in sorted(raw_labels.items(), key=lambda item: int(item[1]))
                ]
            except (TypeError, ValueError):
                return [str(value) for _, value in sorted(raw_labels.items())]

        raise ValueError(f"Unexpected label JSON format in {label_path}")

    @staticmethod
    def _has_builtin_preprocessing(model: Any) -> bool:
        preprocess_classes = {"Rescaling", "Normalization", "CenterCrop", "RandomCrop", "Resizing"}

        def check_layer_list(layers: list[Any], depth: int = 0) -> bool:
            if depth > 3:
                return False
            for layer in layers:
                class_name = layer.__class__.__name__
                layer_name = getattr(layer, "name", "").lower()
                if class_name in preprocess_classes:
                    return True
                if class_name == "Sequential":
                    sublayers = getattr(layer, "layers", [])
                    if sublayers and check_layer_list(sublayers, depth + 1):
                        return True
                if "preprocess" in layer_name or "rescal" in layer_name:
                    return True
            return False

        try:
            return check_layer_list(list(model.layers[:8]))
        except Exception:
            return False

    @staticmethod
    def _run_model_warmup_prediction(artifact: ModelArtifact) -> None:
        try:
            input_shape = getattr(artifact.model, "input_shape", None) or (None, 224, 224, 3)
            height = input_shape[1] if len(input_shape) > 2 and input_shape[1] else 224
            width = input_shape[2] if len(input_shape) > 2 and input_shape[2] else 224
            import numpy as np

            sample = np.zeros((1, int(height), int(width), 3), dtype=np.float32)
            artifact.model.predict(sample, verbose=0)
        except Exception as exc:
            raise RuntimeError(f"warm-up prediction failed: {exc}") from exc

    @staticmethod
    def _crop_name_from_model_file(file_name: str) -> str:
        stem = Path(file_name).stem
        for suffix in (
            "_mobilenet_transfer",
            "_disease",
            "_model",
            "_diseases",
            "_classifier",
        ):
            if stem.lower().endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        return stem

    @staticmethod
    def _normalize_crop_name(crop_name: str) -> str:
        return crop_name.strip().lower()

    @staticmethod
    def _compact(value: str) -> str:
        return value.lower().replace("_", "").replace("-", "").replace(" ", "")

    @staticmethod
    def _cache_key(path: Path) -> str:
        return str(path.resolve()).lower()


model_registry = ModelRegistry()

