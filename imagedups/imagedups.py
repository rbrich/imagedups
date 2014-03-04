import argparse
import os.path
import subprocess
import sys
import time

from imagedups.imagehash import ImageHash
from imagedups.hashdb import HashDB


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

    FORMATS = ['.png', '.jpeg', '.jpg', '.tiff', '.tif']

    def __init__(self):
        self.dbfile = '.imagehash'
        self.parser = argparse.ArgumentParser(
            description=self.__doc__.strip(),
            formatter_class=argparse.RawDescriptionHelpFormatter)
        self.parser.add_argument('path', help='Path to directory of images')
        self.parser.add_argument('--hash', action='store_true', help='Compute hashes of images.')
        self.parser.add_argument('--search', action='store_true', help='Compare hashes, find similars.')
        self.parser.add_argument('--clean', action='store_true', help='Remove files created during --hash phase.')
        self.parser.add_argument('-a', '--algorithm', default='dct', help='Image hash algorithm. Options: dct|mh. Default: dct')
        self.parser.add_argument('-t', '--threshold', type=float, default=90.0, help='Minimal similarity ratio of compared images. Default: 90%%')
        self.parser.add_argument('-f', '--samplefile', help='Search for duplicates of this file.')
        self.parser.add_argument('-r', '--recursive', action='store_true', help='Walk subdirectories recursively.')
        self.parser.add_argument('-x', '--extviewer', action='store_true', help='Use external program to view matching images.')
        self.parser.add_argument('-p', '--program', default='gthumb', help='External program to view images. See -x. Default: gthumb')

    def main(self):
        self.args = self.parser.parse_args()
        self.dbfile += '_' + self.args.algorithm
        self.imagehash_class = ImageHash.get_subclass(self.args.algorithm)
        if self.args.hash or not (self.args.search or self.args.clean):
            self.cmd_hash()
        if self.args.search or not (self.args.hash or self.args.clean):
            self.cmd_search()
        if self.args.clean:
            self.cmd_clean()

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

    def cmd_clean(self):
        if self.args.recursive:
            for dirpath, _filenames in self.walk_directories(self.args.path):
                dbfile = os.path.join(dirpath, self.dbfile)
                self.clean_db(dbfile)
        else:
            dbfile = os.path.join(self.args.path, self.dbfile)
            self.clean_db(dbfile)

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

    def time_changed(self, filename):
        stat = os.stat(filename)
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
                filepath = os.path.join(path, fname)
                if imghash is None or old_hashdb.timestamp < self.time_changed(filepath):
                    try:
                        imghash = self.imagehash_class(filepath)
                    except IOError:
                        continue
                    print(imghash, os.path.join(path, fname))
                new_hashdb.add(fname, imghash)
        finally:
            new_hashdb.save(dbfile)

    def clean_db(self, dbfile):
        hashdb = HashDB(self.imagehash_class)
        try:
            # if it can be loaded, than it's our database
            hashdb.load(dbfile)
        except IOError:
            return
        os.unlink(dbfile)

    def search_db_for_dups(self, hashdb):
        last_fname = None
        i = 1
        file_list = []
        threshold = 1.0 - (self.args.threshold / 100)
        for fname_a, fname_b, distance in hashdb.find_all_dups(threshold):
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
        imghash = self.imagehash_class(samplefile)
        print(samplefile)
        file_list = [samplefile]
        threshold = 1.0 - (self.args.threshold / 100)
        for fname, distance in hashdb.query(imghash, threshold):
            self.print_out(fname, distance)
            file_list.append(fname)
        self.view(file_list)

    def print_out(self, fname, distance):
        similarity = (1.0 - distance) * 100.0
        print(fname, '(%.0f%%)' % similarity)

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

