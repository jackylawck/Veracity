import inspect
import pkgutil
import pytest
import adapters
from adapters.base import BaseAdapter

def get_all_adapters():
    classes = []
    for _, module_name, _ in pkgutil.iter_modules(adapters.__path__):
        if module_name == "base":
            continue
        mod = __import__(f"adapters.{module_name}", fromlist=[module_name])
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, BaseAdapter) and obj is not BaseAdapter:
                classes.append(obj)
    return classes

@pytest.mark.parametrize("cls", get_all_adapters(), ids=lambda c: getattr(c, "NAME", c.__name__))
def test_adapter_interface(cls):
    """確保所有 74 個適配器均具備合規屬性與方法"""
    assert hasattr(cls, "NAME"), f"{cls.__name__} 缺少 NAME"
    inst = cls()
    assert hasattr(inst, "fetch_records"), f"{cls.__name__} 缺少 fetch_records"
