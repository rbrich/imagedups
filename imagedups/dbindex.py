class DBIndex:

    def __init__(self, filename=None):
        self._filename = None
        self._seqnext = 1
        self._items = []
        self._map_path_to_name = {}
        if filename:
            try:
                self.load(filename)
            except IOError:
                pass

    def load(self, filename):
        self._filename = filename
        with open(filename, 'r', encoding='utf8') as f:
            for line in f:
                if line[0] == '#':
                    self._parse_control_line(line)
                elif line.strip() == '':
                    continue
                else:
                    name, path = line.rstrip('\n').split(' ', 1)
                    self._add(name, path)

    def save(self, filename=None):
        with open(filename or self._filename, 'w', encoding='utf8') as f:
            print('#seqnext', self._seqnext, file=f)
            for name, path in self._items:
                print(name, path, file=f)

    def get_name_by_path(self, path):
        if path in self._map_path_to_name:
            return self._map_path_to_name[path]
        return self.add(path)

    def items(self):
        for name, path in self._items:
            yield name, path

    def add(self, path):
        """Add path to index, return its name."""
        name = str(self._seqnext)
        self._seqnext += 1
        self._add(name, path)
        return name

    def _add(self, name, path):
        self._items.append((name, path))
        self._map_path_to_name[path] = name

    def _parse_control_line(self, line):
        parts = line.split(' ')
        if len(parts) == 2 and parts[0] == '#seqnext':
            self._seqnext = int(parts[1])
