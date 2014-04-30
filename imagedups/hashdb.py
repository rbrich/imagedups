from collections import OrderedDict
import time
import os


class HashDB:
    def __init__(self, imagehash_class):
        self._hashes = OrderedDict()
        self._timestamp = int(time.time())
        self._imagehash_class = imagehash_class

    @property
    def timestamp(self):
        """Time of hash database creation."""
        return self._timestamp

    def add(self, fname, imghash):
        """Add hash to database.

        Args:
            fname: File name of image hashed, should not contain path.
            imghash: Instance of ImageHash.

        """
        self._hashes[fname] = imghash

    def get(self, fname):
        """Get hash from database.

        If not found, returns None.

        """
        if fname in self._hashes:
            return self._hashes[fname]

    def save(self, dbfile):
        """Save database to file.

        Empty database is "saved" as no file.
        Existing file is overwritten or removed.

        Args:
            dbfile: Target file name, including path.

        """
        if not self._hashes:
            try:
                os.unlink(dbfile)
            except OSError:
                pass
            return
        with open(dbfile, 'w', encoding='utf8') as f:
            print('#algorithm', self._imagehash_class.algorithm(), file=f)
            print('#timestamp', self._timestamp, file=f)
            for fname, imghash in self._hashes.items():
                print(imghash, fname, file=f)

    def load(self, dbfile, path=''):
        """Load database from file.

        Args:
            dbfile: Source file, including path.
            path: Path do prepend to all file names loaded from file.

        """
        with open(dbfile, 'r', encoding='utf8') as f:
            for line in f:
                if line[0] == '#':
                    self._parse_control_line(line)
                else:
                    hexhash, fname = line.rstrip().split(' ', 1)
                    imghash = self._imagehash_class()
                    imghash.load(hexhash)
                    self.add(os.path.join(path, fname), imghash)

    def query(self, imghash, threshold=0.0):
        """Find images close to given hash."""
        for fname, hash_b in self._hashes.items():
            distance = imghash.distance(hash_b)
            if distance <= threshold:
                yield fname, distance

    def find_all_dups(self, threshold=0.0):
        """Find similar images in database.

        Returns:
            Generator of tuples (fname_a, fname_b, distance).
            fname_a, fname_b: File names of pair of similar images.
            distance: Normalized distance of hashes.

        Returned pairs are sorted by fname_a.

        """
        hash_items = list(self._hashes.items())
        for idx, (fname_a, hash_a) in enumerate(hash_items):
            for fname_b, hash_b in hash_items[idx+1:]:
                distance = hash_a.distance(hash_b)
                if distance <= threshold:
                    yield fname_a, fname_b, distance

    def find_all_dups_without_derived(self, threshold=0.0):
        """Find similar images in database, skipping derived pairs.

        This is variant of :meth:`find_all_dups`, which avoids
        reporting subsets of already reported groups.
        For example: (x,a), (x,b), ... avoids (a,b) later.

        """
        reported = dict()
        for fname_a, fname_b, distance in self.find_all_dups(threshold):
            for key in reported:
                if fname_a in reported[key] and fname_b in reported[key]:
                    # If both A and B were reported before as duplicates of X,
                    # skip this pair
                    break
            else:
                yield fname_a, fname_b, distance
                if not fname_a in reported:
                    reported[fname_a] = set()
                reported[fname_a].add(fname_b)

    def _parse_control_line(self, line):
        parts = line.split(' ')
        if len(parts) == 2 and parts[0] == '#timestamp':
            self._timestamp = int(parts[1])

