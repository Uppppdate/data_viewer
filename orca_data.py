"""Data model wrapper around the parsed JSON."""
import json


class OrcaData:
    def __init__(self, path=None):
        self.raw = {}
        self.path = None
        if path:
            self.load(path)

    def load(self, path):
        with open(path, "r", encoding="utf-8") as f:
            self.raw = json.load(f)
        self.path = path

    def keys(self):
        return list(self.raw.keys())

    def get(self, key):
        return self.raw.get(key, {})