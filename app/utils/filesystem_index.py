"""Directory snapshots scoped to one dataset load, avoiding per-file network stats."""

import os


class DirectoryIndex:
    """Read each directory once; create a new index for every dataset reload."""

    def __init__(self):
        self._directories = {}

    def entries(self, directory):
        key = os.path.abspath(directory)
        if key not in self._directories:
            try:
                with os.scandir(key) as entries:
                    self._directories[key] = {entry.name: entry for entry in entries}
            except (FileNotFoundError, NotADirectoryError):
                self._directories[key] = {}
            except OSError:
                # Preserve normal stat behavior if a directory cannot be listed.
                self._directories[key] = None
        return self._directories[key]

    def exists(self, path):
        if not path:
            return False
        normalized = os.path.abspath(path)
        parent, name = os.path.split(normalized)
        if not name:
            return os.path.exists(path)
        entries = self.entries(parent)
        if entries is None:
            return os.path.exists(path)
        entry = entries.get(name)
        if entry is None:
            return False
        # A directory entry alone does not prove a symlink's target exists.
        return os.path.exists(path) if entry.is_symlink() else True

    def files(self, directory, extensions):
        entries = self.entries(directory)
        if entries is None:
            return []
        return [
            os.path.join(directory, name)
            for name, entry in entries.items()
            if os.path.splitext(name)[1].lower() in extensions and entry.is_file()
        ]
