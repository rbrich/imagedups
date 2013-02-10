#!/usr/bin/env python3

import phash
import argparse
import os.path
import subprocess
import sys
import time
from collections import OrderedDict

from imagedups.imagehash import ImageHash


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

        Returned pairs may be grouped by fname_a.

        """
        hash_items = list(self._hashes.items())
        reported = set()
        for idx, (fname_a, hash_a) in enumerate(hash_items):
            if fname_a in reported:
                # this avoids reporting subsets of already reported groups
                # For example: (a,x), (a,y), ... avoids (x,y) later
                continue
            for fname_b, hash_b in hash_items[idx+1:]:
                distance = hash_a.distance(hash_b)
                if distance <= threshold:
                    reported.add(fname_b)
                    yield fname_a, fname_b, distance

    def _parse_control_line(self, line):
        parts = line.split(' ')
        if len(parts) == 2 and parts[0] == '#timestamp':
            self._timestamp = int(parts[1])


class ImageDups:

    """Finds duplicate images using pHash library

    Algorithm has two parts:
        * compute hashes of images
        * compare hashes

    To compute hashes, use '--hash' command. Computed hashes are written to file
    named .phash in target directory.

    To compare hashes and search for duplicates, use '--search' command. This reads
    .phash file, compares each hash with each other and prints out pairs of images
    with hash distance up to threshold.

    Both phases are run unless one of --hash or --search commands is given.

    """

    FORMATS = ['.jpeg', '.jpg', '.tiff', '.tif']

    def __init__(self):
        self.dbfile = '.imagehash'
        self.parser = argparse.ArgumentParser(
            description=self.__doc__.strip(),
            formatter_class=argparse.RawDescriptionHelpFormatter)
        self.parser.add_argument('path', help='Path to directory of images')
        self.parser.add_argument('--hash', action='store_true', help='Compute hashes of images')
        self.parser.add_argument('--search', action='store_true', help='Compare hashes, find similars')
        self.parser.add_argument('-a', '--algorithm', default='dct', help='Image hash algorithm. Options: dct|mh. Default: dct.')
        self.parser.add_argument('-t', '--threshold', type=float, default=0.1, help='Maximum normalized distance of compared images. Default: 0.1')
        self.parser.add_argument('-f', '--samplefile', help='Search for duplicates of this file.')
        self.parser.add_argument('-r', '--recursive', action='store_true', help='Walk subdirectories recursively.')
        self.parser.add_argument('-x', '--extviewer', action='store_true', help='Use external program to view matching images.')
        self.parser.add_argument('-p', '--program', default='gthumb', help='External program to view images. See -x. Default: gthumb.')

    def main(self):
        self.args = self.parser.parse_args()
        self.dbfile += '_' + self.args.algorithm
        self.imagehash_class = ImageHash.get_subclass(self.args.algorithm)
        if self.args.hash or not self.args.search:
            self.cmd_hash()
        if self.args.search or not self.args.hash:
            self.cmd_search()

    def cmd_hash(self):
        if self.args.recursive:
            for dirpath, filenames in self.walk_directories(self.args.path):
                dbfile = os.path.join(dirpath, self.dbfile)
                self.update_db(dirpath, filenames, dbfile)
        else:
            filenames = self.list_images(self.args.path)
            dbfile = os.path.join(self.args.path, self.dbfile)
            self.update_db(self.args.path, filenames, dbfile)

    def cmd_search(self):
        hashdb = HashDB(self.imagehash_class)
        if self.args.recursive:
            for dirpath, _filenames in self.walk_directories(self.args.path):
                dbfile = os.path.join(dirpath, self.dbfile)
                try:
                    hashdb.load(dbfile, dirpath)
                except IOError:
                    pass
        else:
            dbfile = os.path.join(self.args.path, self.dbfile)
            try:
                hashdb.load(dbfile, self.args.path)
            except IOError:
                pass
        if self.args.samplefile:
            self.compare_with_db(hashdb, self.args.samplefile)
        else:
            self.search_db_for_dups(hashdb)

    def walk_directories(self, path):
        for dirpath, _dirnames, filenames in os.walk(path):
            filenames = [fname for fname in filenames if self.is_image(fname)]
            filenames.sort()
            yield dirpath, filenames

    def list_images(self, path):
        for fname in sorted(os.listdir(path)):
            if self.is_image(fname):
                yield fname

    def is_image(self, fname):
        _root, ext = os.path.splitext(fname)
        if ext.lower() in self.FORMATS:
            return True

    def time_changed(self, file):
        stat = os.stat(file)
        return int(max(stat.st_ctime, stat.st_mtime))

    def update_db(self, path, filenames, dbfile, rebuild=False):
        old_hashdb = HashDB(self.imagehash_class)
        new_hashdb = HashDB(self.imagehash_class)
        if not rebuild:
            try:
                old_hashdb.load(dbfile)
            except IOError:
                pass
        try:
            for fname in filenames:
                imghash = old_hashdb.get(fname)
                file = os.path.join(path, fname)
                if imghash is None or old_hashdb.timestamp < self.time_changed(file):
                    try:
                        imghash = self.imagehash_class()
                        imghash.compute(file)
                    except IOError:
                        continue
                    print(imghash, os.path.join(path, fname))
                new_hashdb.add(fname, imghash)
        finally:
            new_hashdb.save(dbfile)

    def search_db_for_dups(self, hashdb):
        last_fname = None
        i = 1
        file_list = []
        for fname_a, fname_b, distance in hashdb.find_all_dups(self.args.threshold):
            if fname_a != last_fname:
                if self.view(file_list, test_stop=True):
                    file_list = []
                    break
                print('---', i, '---')
                print(fname_a)
                file_list = [fname_a]
                last_fname = fname_a
                i += 1
            file_list.append(fname_b)
            self.print_out(fname_b, distance)
        self.view(file_list)

    def compare_with_db(self, hashdb, samplefile):
        imghash = phash.dct_imagehash(samplefile)
        print(samplefile)
        file_list = [samplefile]
        for fname, distance in hashdb.query(imghash, self.args.threshold):
            self.print_out(fname, distance)
            file_list.append(fname)
        self.view(file_list)

    def print_out(self, fname, distance):
        if distance == 0:
            print(fname, '(equal)')
        else:
            print(fname, '(distance %.1f%%)' % (distance*100.))

    def view(self, file_list, test_stop=False):
        if file_list and self.args.extviewer:
            print('* Waiting for subprocess...', end='')
            sys.stdout.flush()
            with open(os.devnull, "w") as devnull:
                subprocess.call([self.args.program] + file_list, stdout=devnull, stderr=devnull)
            print('\r' + ' '*30 + '\r', end='')
            if test_stop and self.test_stop():
                return True

    def test_stop(self):
        print('* Press Ctrl-C to stop', end='')
        sys.stdout.flush()
        try:
            for _i in range(3):
                time.sleep(0.5)
                print('.', end='')
                sys.stdout.flush()
        except KeyboardInterrupt:
            print()
            return True
        print('\r' + ' '*30 + '\r', end='')


prog = ImageDups()
try:
    prog.main()
except KeyboardInterrupt:
    print('Interrupted...')

