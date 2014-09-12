import argparse
import os.path
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor as PoolExecutor
from concurrent.futures import Future

from imagedups.imagehash import ImageHash, compute_hash
from imagedups.hashdb import HashDB
from imagedups.dbindex import DBIndex


class ImageDups:

    """Finds duplicate images using pHash library

    Algorithm has two parts:
        * compute hashes of images
        * compare hashes

    To compute hashes, use '--hash' command. Computed hashes are written
    to hash database in '~/.imagedups' directory.
    Use '-r' option for recursive search of images in subdirectories.

    To compare hashes and search for duplicates, use '--search' command.
    This reads hash database, compares each hash with each other
    and prints out pairs of images with hash distance up to threshold.

    Both phases are run in succession if no command is given.

    To clean the hash database, use '--clean' command
    or just remove '~/.imagedups' directory.

    """

    FORMATS = ['.png', '.jpeg', '.jpg', '.tiff', '.tif']

    def __init__(self):
        self.dbfile = '.imagehash'
        self.parser = argparse.ArgumentParser(
            description=self.__doc__.strip(),
            formatter_class=argparse.RawDescriptionHelpFormatter)
        self.parser.add_argument('path', nargs='?', help='Path to directory of images')
        self.parser.add_argument('--hash', action='store_true', help='Compute hashes of images.')
        self.parser.add_argument('--search', action='store_true', help='Compare hashes, find similar images.')
        self.parser.add_argument('--clean', action='store_true', help='Remove files created during --hash phase.')
        self.parser.add_argument('-a', '--algorithm', default='dct', help='Image hash algorithm. Options: dct | mh | radial. Default: dct')
        self.parser.add_argument('-t', '--threshold', type=float, default=90.0, help='Minimal similarity ratio of compared images. Default: 90%%')
        self.parser.add_argument('-f', '--samplefile', help='Search for duplicates of this file.')
        self.parser.add_argument('-r', '--recursive', action='store_true', help='Walk subdirectories recursively.')
        self.parser.add_argument('-i', '--inplace', action='store_true', help='Write .imagehash file in same directory where images reside.')
        self.parser.add_argument('-x', '--extviewer', action='store_true', help='Use external program to view matching images.')
        self.parser.add_argument('-p', '--program', default='gthumb', help='External program to view images. See -x. Default: gthumb')
        self.parser.add_argument('--dbpath', default='~/.imagedups', help='Path where database files will be written and read from.')

    def main(self):
        self.args = self.parser.parse_args()
        self.args.dbpath = os.path.expanduser(self.args.dbpath)
        os.makedirs(self.args.dbpath, exist_ok=True)
        self.dbfile += '_' + self.args.algorithm
        self.imagehash_class = ImageHash.get_subclass(self.args.algorithm)
        if self.args.hash or not (self.args.search or self.args.clean):
            self.cmd_hash()
        if self.args.search or not (self.args.hash or self.args.clean):
            self.cmd_search()
        if self.args.clean:
            self.cmd_clean()

    def cmd_hash(self):
        if not self.args.path:
            print('Path must be specified')
            return
        dbindex = DBIndex(os.path.join(self.args.dbpath, 'index'))
        try:
            for dirpath, filenames in self.all_directories_with_filenames():
                if not self.args.inplace:
                    name = dbindex.get_name_by_path(dirpath)
                    dbfile = os.path.join(self.args.dbpath, name + self.dbfile)
                else:
                    dbfile = os.path.join(dirpath, self.dbfile)
                self.update_db(dirpath, filenames, dbfile)
        finally:
            dbindex.save()

    def cmd_search(self):
        dbindex = DBIndex(os.path.join(self.args.dbpath, 'index'))
        hashdb = HashDB(self.imagehash_class)
        if self.args.path:
            # Search for duplicates in path
            for dirpath in self.all_directories():
                inplace_dbfile = os.path.join(dirpath, self.dbfile)
                name = dbindex.get_name_by_path(dirpath)
                home_dbfile = os.path.join(self.args.dbpath, name + self.dbfile)
                hashdb.try_load(inplace_dbfile, home_dbfile, basepath=dirpath)
        else:
            # Search for duplicates in all hashed images from database
            for name, path in dbindex.items():
                home_dbfile = os.path.join(self.args.dbpath, name + self.dbfile)
                hashdb.try_load(home_dbfile, basepath=path)
        if self.args.samplefile:
            self.compare_with_db(hashdb, self.args.samplefile)
        else:
            self.search_db_for_dups(hashdb)

    def cmd_clean(self):
        for dirpath in self.all_directories():
            dbfile = os.path.join(dirpath, self.dbfile)
            self.clean_db(dbfile)

    def all_directories(self):
        if self.args.recursive:
            for dirpath, _dirnames, _filenames in os.walk(self.args.path):
                yield dirpath
        else:
            yield self.args.path

    def all_directories_with_filenames(self):
        if self.args.recursive:
            for dirpath, _dirnames, filenames in os.walk(self.args.path):
                filenames = [fname for fname in filenames if self.is_image(fname)]
                filenames.sort()
                yield dirpath, filenames
        else:
            filenames = self.list_images(self.args.path)
            yield self.args.path, filenames

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
        print('Hashing', path)
        hashdb = HashDB(self.imagehash_class)
        if not rebuild:
            # Load existing database file
            try:
                hashdb.load(dbfile)
            except IOError:
                pass
        with PoolExecutor(max_workers=os.cpu_count() or 4) as executor:
            # Compute hashes for new or updated files
            hashes = []
            for fname in filenames:
                imghash = hashdb.get(fname)
                filepath = os.path.join(path, fname)
                if imghash is None or hashdb.timestamp < self.time_changed(filepath):
                    future_imghash = executor.submit(compute_hash,
                                                     self.imagehash_class, filepath)
                    hashes.append((fname, future_imghash))
                else:
                    hashes.append((fname, imghash))
            # Reset database, then add new hashes
            hashdb.clear()
            for fname, imghash in hashes:
                if isinstance(imghash, Future):
                    imghash = imghash.result(timeout=60)
                if imghash:
                    hashdb.add(fname, imghash)
        hashdb.save(dbfile)

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
        for fname_a, fname_b, distance in hashdb.find_all_dups_without_derived(threshold):
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
        """Display files from `file_list` using external program.

        Waits for external program to exit before continuing.

        """
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

