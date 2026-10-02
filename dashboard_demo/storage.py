"""Local JSON storage for operator reviews."""

import fcntl
import json
import os
import tempfile
from pathlib import Path


class ReviewStore:
    def __init__(self, path):
        self.path = Path(path)

    def get(self, case_id):
        if not self.path.exists():
            return None
        with self.path.open(encoding="utf-8") as file:
            return json.load(file).get(str(case_id))

    def add(self, case_id, review):
        return self._write(case_id, review, replace=False)

    def update(self, case_id, review):
        return self._write(case_id, review, replace=True)

    def _write(self, case_id, review, replace):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with (self.path.parent / (self.path.name + ".lock")).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = {}
            if self.path.exists():
                with self.path.open(encoding="utf-8") as file:
                    data = json.load(file)
            key = str(case_id)
            if replace:
                if key not in data or data[key].get("status") != "awaiting_survey":
                    return False
            elif key in data:
                return False
            data[key] = review
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=self.path.parent, delete=False
                ) as file:
                    temporary = file.name
                    json.dump(data, file, ensure_ascii=False, indent=2)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, self.path)
            finally:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)
            return True
