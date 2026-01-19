from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path

class MetadataMixin:
    """Domain methods extracted from the original SaveExtractor."""

    def get_metadata(self) -> dict:
        """Get basic save metadata.

        Returns:
            Dict with empire name, date, version, etc.
        """
        result = {
            'file_path': str(self.save_path),
            'file_size_mb': self.save_path.stat().st_size / (1024 * 1024),
            'modified': datetime.fromtimestamp(self.save_path.stat().st_mtime).isoformat(),
            'gamestate_loaded': getattr(self, "_gamestate", None) is not None,
        }
        if getattr(self, "_gamestate", None) is not None:
            result["gamestate_chars"] = len(self.gamestate)

        # Parse meta file
        for line in self.meta.split('\n'):
            if '=' in line and 'flag' not in line.lower():
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip().strip('"')
                if key in ['version', 'name', 'date']:
                    result[key] = value

        return result
