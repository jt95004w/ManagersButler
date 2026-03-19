from __future__ import annotations

import copy
import json
from dataclasses import MISSING, asdict, dataclass, field, fields, is_dataclass
from typing import Any, get_args, get_origin


class FieldInfo:
    def __init__(self, default=MISSING, default_factory=MISSING):
        self.default = default
        self.default_factory = default_factory


def Field(default=MISSING, default_factory=MISSING):
    return FieldInfo(default=default, default_factory=default_factory)


def computed_field(func):
    return property(func)


class BaseModel:
    def __init_subclass__(cls, **kwargs):
        annotations = getattr(cls, '__annotations__', {})
        new_fields = []
        for name in annotations:
            default = getattr(cls, name, MISSING)
            if isinstance(default, property):
                continue
            if isinstance(default, FieldInfo):
                if default.default_factory is not MISSING:
                    new_fields.append((name, annotations[name], field(default_factory=default.default_factory)))
                elif default.default is not MISSING:
                    new_fields.append((name, annotations[name], field(default=default.default)))
                else:
                    new_fields.append((name, annotations[name]))
            elif default is MISSING:
                new_fields.append((name, annotations[name]))
            else:
                new_fields.append((name, annotations[name], field(default=default)))
        namespace = {k: v for k, v in cls.__dict__.items() if k not in annotations}
        dc = dataclass(eq=False)(type(cls.__name__, cls.__bases__, namespace))
        dc.__annotations__ = annotations
        for item in reversed(new_fields):
            pass
        # rebuild via make_dataclass semantics manually
        import dataclasses
        dc = dataclasses.make_dataclass(cls.__name__, new_fields, bases=cls.__bases__, namespace=namespace, eq=False)
        cls.__dataclass_fields__ = dc.__dataclass_fields__
        cls.__init__ = dc.__init__
        cls.__repr__ = dc.__repr__

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def model_validate(cls, data: Any):
        kwargs = {}
        for f in fields(cls):
            value = data.get(f.name)
            kwargs[f.name] = _coerce(value, f.type)
        return cls(**kwargs)

    @classmethod
    def model_validate_json(cls, data: str):
        return cls.model_validate(json.loads(data))

    def model_copy(self, update: dict | None = None, deep: bool = False):
        payload = self.model_dump()
        if update:
            payload.update(update)
        return self.__class__.model_validate(copy.deepcopy(payload) if deep else payload)


def _coerce(value: Any, annotation: Any):
    origin = get_origin(annotation)
    args = get_args(annotation)
    if value is None:
        return None
    if origin is list and args:
        inner = args[0]
        return [_coerce(item, inner) for item in value]
    if origin is dict:
        return value
    if origin is None and isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation.model_validate(value)
    if origin is not None and type(None) in args:
        actual = next((a for a in args if a is not type(None)), Any)
        return _coerce(value, actual)
    return value
