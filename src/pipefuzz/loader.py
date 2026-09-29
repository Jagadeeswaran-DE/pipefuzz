"""Transformation target resolution and signature validation."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import inspect
import sys
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

from pipefuzz.errors import ConfigurationError
from pipefuzz.models import Transformation


def split_target(target: str) -> tuple[str, str]:
    module_ref, separator, function_name = target.rpartition("::")
    if not separator or not module_ref or not function_name or "." in function_name:
        raise ConfigurationError("Target must use <file-or-module>::<function>")
    return module_ref, function_name


def discover_config_path(target: str, cwd: Path) -> Path:
    module_ref, _ = split_target(target)
    candidate = Path(module_ref)
    if candidate.suffix == ".py" or candidate.exists() or "/" in module_ref or "\\" in module_ref:
        file_path = candidate if candidate.is_absolute() else cwd / candidate
        return file_path.resolve().parent / "pipefuzz.yaml"
    return cwd / "pipefuzz.yaml"


def _local_module_names(parent: Path) -> set[str]:
    return {
        child.stem if child.is_file() else child.name
        for child in parent.iterdir()
        if (child.is_file() and child.suffix == ".py" and child.stem != "__init__")
        or (child.is_dir() and (child / "__init__.py").is_file())
    }


@contextmanager
def _scoped_file_imports(parent: Path):
    """Resolve sibling imports from this file's directory without cache collisions."""
    names = _local_module_names(parent)

    def is_local_name(name: str) -> bool:
        return any(name == root or name.startswith(root + ".") for root in names)

    displaced = {name: module for name, module in sys.modules.items() if is_local_name(name)}
    for name in displaced:
        sys.modules.pop(name, None)
    parent_text = str(parent)
    sys.path.insert(0, parent_text)
    try:
        yield
    finally:
        sys.path.remove(parent_text)
        for name in tuple(sys.modules):
            if is_local_name(name):
                sys.modules.pop(name, None)
        sys.modules.update(displaced)


def _load_file(path: Path):
    resolved = path.resolve()
    if not resolved.is_file():
        raise ConfigurationError(f"Transformation file does not exist: {resolved}")
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:12]
    module_name = f"_pipefuzz_target_{digest}"
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        raise ConfigurationError(f"Could not create an import spec for {resolved}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        with _scoped_file_imports(resolved.parent):
            spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise ConfigurationError(f"Could not import transformation file {resolved}: {exc}") from exc
    return module


def load_transformation(target: str, input_names: tuple[str, ...], cwd: Path | None = None) -> Transformation:
    module_ref, function_name = split_target(target)
    current = cwd or Path.cwd()
    candidate = Path(module_ref)
    try:
        if candidate.suffix == ".py" or candidate.exists() or "/" in module_ref or "\\" in module_ref:
            path = candidate if candidate.is_absolute() else current / candidate
            module = _load_file(path)
        else:
            module = importlib.import_module(module_ref)
    except ConfigurationError:
        raise
    except Exception as exc:
        raise ConfigurationError(f"Could not import transformation module {module_ref!r}: {exc}") from exc
    transformation = getattr(module, function_name, None)
    if not callable(transformation):
        raise ConfigurationError(f"Target attribute {function_name!r} is not callable")
    try:
        inspect.signature(transformation).bind(**{name: object() for name in input_names})
    except TypeError as exc:
        raise ConfigurationError(
            "Transformation must accept keyword arguments matching configured input names: "
            + ", ".join(input_names)
        ) from exc
    if candidate.suffix == ".py" or candidate.exists() or "/" in module_ref or "\\" in module_ref:
        @wraps(transformation)
        def scoped_transformation(*args, **kwargs):
            with _scoped_file_imports(path.resolve().parent):
                return transformation(*args, **kwargs)

        return scoped_transformation
    return transformation
