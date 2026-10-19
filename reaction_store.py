"""Session-level store for saved reactions.

A module-level singleton means reactions survive closing and reopening
the Analysis window (and even a JSON reload, since MainWindow is
recreated but the module is not).
"""


class ReactionStore:
    def __init__(self):
        self.reactions = []

    def add(self, reaction):
        self.reactions.append(reaction)

    def remove(self, index):
        if 0 <= index < len(self.reactions):
            del self.reactions[index]

    def __iter__(self):
        return iter(self.reactions)

    def __len__(self):
        return len(self.reactions)


_store = ReactionStore()


def get_store():
    return _store