#!/usr/bin/env python3

import phash
import argparse
import os.path
import subprocess
import sys
import time
from collections import OrderedDict


class HashDB:
    def __init__(self):
        self._hashes = OrderedDict()

    def add(self, fname, imghash):
        self._hashes[fname] = imghash

    def get(self, fname):
        if fname in self._hashes:
            return self._hashes[fname]

    def save(self, dbfile):
        if not self._hashes:
            return
        with open(dbfile, 'w', encoding='utf8') as f:
            for fname, imghash in self._hashes.items():
                print('%016X' % imghash, fname, file=f)

    def load(self, dbfile, path=''):
        with open(dbfile, 'r', encoding='utf8') as f:
            for line in f:
                hexhash, fname = line.rstrip().split(' ')
                imghash = int(hexhash, 16)
                self.add(os.path.join(path, fname), imghash)

    def query(self, imghash, threshold=0):
        for fname, hash_b in self._hashes.items():
            distance = phash.hamming_distance(imghash, hash_b)
            if distance <= threshold:
                yield fname, distance

    def find_all_dups(self, threshold=0):
        hash_items = list(self._hashes.items())
        for idx, (fname_a, hash_a) in enumerate(hash_items):
            for fname_b, hash_b in hash_items[idx+1:]:
                distance = phash.hamming_distance(hash_a, hash_b)
                if distance <= threshold:
                    yield fname_a, fname_b, distance


class ImageDups:

    """Finds duplicate images using pHash library

    Algorithm has two parts:
        * compute hash of images
        * compare hashes

    To compute hashes, use 'hash' command. Computed hashes are written to file
    named .phash in target directory.

    To compare hashes and search for duplicates, use 'search' command. This reads
    .phash file, compares each hash with each other and prints out pairs of images
    with hash distance up to threshold.

    Program works with images in one directory, not including subdirectories.

    """

    FORMATS = ['.jpg']
    DBFILE = '.imagephash'

    def __init__(self):
        self.parser = argparse.ArgumentParser(
            description=self.__doc__.strip(),
            formatter_class=argparse.RawDescriptionHelpFormatter)
        self.parser.add_argument('cmd', help='Command: hash, search')
        self.parser.add_argument('path', help='Path to directory of images')
        self.parser.add_argument('-t', '--threshold', type=int, default=5, help='Maximum distance of compared images.')
        self.parser.add_argument('-f', '--samplefile', help='Search for duplicates of this file.')
        self.parser.add_argument('-r', '--recursive', action='store_true', help='Walk subdirectories recursively.')
        self.parser.add_argument('-x', '--extviewer', action='store_true', help='Open images in external viewer.')

    def main(self):
        self.args = self.parser.parse_args()
        if self.args.cmd == 'hash':
            self.cmd_hash()
        elif self.args.cmd == 'search':
            self.cmd_search()
        else:
            raise Exception('Unknown command: %s' % self.args.cmd)

    def cmd_hash(self):
        if self.args.recursive:
            for dirpath, filenames in self.walk_directories(self.args.path):
                dbfile = os.path.join(dirpath, self.DBFILE)
                self.update_db(dirpath, filenames, dbfile)
        else:
            filenames = self.list_images(self.args.path)
            dbfile = os.path.join(self.args.path, self.DBFILE)
            self.update_db(self.args.path, filenames, dbfile)

    def cmd_search(self):
        hashdb = HashDB()
        if self.args.recursive:
            for dirpath, _filenames in self.walk_directories(self.args.path):
                dbfile = os.path.join(dirpath, self.DBFILE)
                try:
                    hashdb.load(dbfile, dirpath)
                except IOError:
                    pass
        else:
            dbfile = os.path.join(self.args.path, self.DBFILE)
            hashdb.load(dbfile, self.args.path)
        if self.args.samplefile:
            self.compare_with_db(hashdb, self.args.samplefile)
        else:
            self.search_db_for_dups(hashdb)

    def walk_directories(self, path):
        for dirpath, _dirnames, filenames in os.walk(path):
            yield dirpath, [fname for fname in filenames if self.is_image(fname)]

    def list_images(self, path):
        for fname in sorted(os.listdir(path)):
            if self.is_image(fname):
                yield fname

    def is_image(self, fname):
        _root, ext = os.path.splitext(fname)
        if ext.lower() in self.FORMATS:
            return True

    def update_db(self, path, filenames, dbfile, rebuild=False):
        old_hashdb = HashDB()
        new_hashdb = HashDB()
        if not rebuild:
            try:
                old_hashdb.load(dbfile)
            except IOError:
                pass
        for fname in filenames:
            imghash = old_hashdb.get(fname)
            if imghash is None:
                try:
                    imghash = phash.dct_imagehash(os.path.join(path, fname))
                except IOError:
                    continue
                print('%016X' % imghash, os.path.join(path, fname))
            new_hashdb.add(fname, imghash)
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
        file_list = []
        for fname, distance in hashdb.query(imghash, self.args.threshold):
            self.print_out(self, fname, distance)
            file_list.append(fname)
        self.view(file_list)

    def print_out(self, fname, distance):
        if distance == 0:
            print(fname, '(equal)')
        else:
            print(fname, '(distance %d)' % distance)

    def view(self, file_list, test_stop=False):
        if file_list and self.args.extviewer:
            print('* Waiting for subprocess...', end='')
            sys.stdout.flush()
            with open(os.devnull, "w") as devnull:
                subprocess.call(['gthumb'] + file_list, stdout=devnull, stderr=devnull)
            print('\r' + ' '*30 + '\r', end='')
            if test_stop and self.test_stop():
                return True

    def test_stop(self):
        print('* Press Ctrl-C to stop', end='')
        sys.stdout.flush()
        try:
            for _i in range(4):
                time.sleep(0.5)
                print('.', end='')
                sys.stdout.flush()
        except KeyboardInterrupt:
            print()
            return True
        print('\r' + ' '*30 + '\r', end='')


prog = ImageDups()
prog.main()

