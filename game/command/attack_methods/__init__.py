
"""Every module in this folder defines one attack method. They are imported here so that they register themselves."""
import importlib
import pkgutil

for _name in sorted(info.name for info in pkgutil.iter_modules(__path__) if not info.name.startswith("_")):
    importlib.import_module(f"{__name__}.{_name}")