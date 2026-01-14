"""Stellaris save extraction package.

The main entrypoint is `stellaris_save_extractor.SaveExtractor`.

Compatibility import `from save_extractor import SaveExtractor` is preserved
via the top-level `save_extractor.py` module.
"""

from .extractor import SaveExtractor

__all__ = ["SaveExtractor"]

