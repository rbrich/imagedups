from argparse import ArgumentParser, RawDescriptionHelpFormatter
import os.path
import sys
import json
import gzip
from concurrent.futures import ThreadPoolExecutor as PoolExecutor

from dedupimages.imagehash import ImageHash, compute_hash
from dedupimages.hashdb import HashDB
from dedupimages.config import Config


class DedupImages:

    """Finds duplicate images using pHash library

    Algorithm has two parts:
        * compute hashes of images
        * compare hashes

    To compute hashes, use '--hash' command. Computed hashes are written
    to hash database in '~/.cache/dedup-images.hashdb' file.
    Use '-r' option for recursive search of images in subdirectories.

    To compare hashes and search for duplicates, use '--search' command.
    This reads hash database, compares each hash with each other
    and prints out groups of images with hash distance lesser than a threshold.

    When original image files are moved, modified or deleted, their hashes
    stay in database and '--search' would still report them. Use '--cleanup'
    command to remove dead references from database. This removes the file
    references, so they are no longer reported, but keeps actual hashes.
    When the same file is found elsewhere by '--hash', it just adds the file
    name to this dead item, thus handling file renames.

    Use '--prune' command to remove any items without file references
    from database. This is not needed unless the database grows too much.

    Order of command execution is fixed (not affected by order of arguments):

    1. remove
    2. hash
    3. cleanup
    4. prune
    5. search

    By default, if no command is specified, the following are run:
    hash, cleanup, search

    """

    FORMATS = ['.png', '.jpeg', '.jpg', '.tiff', '.tif']

    def __init__(self, cfg: Config):
        self.algorithm = cfg.algorithm
        self.threshold = cfg.threshold
        self.viewer = cfg.viewer
        self.dbpath = cfg.dbpath
        self.hashdb = HashDB()

    def process_args(self):
        # Process program args
        ap = ArgumentParser(description=self.__doc__.strip(),
                            formatter_class=RawDescriptionHelpFormatter)
        ap.add_argument('path', nargs='?',
                        help='Target directory to be hashed / searched')
        ap.add_argument('--hash', action='store_true',
                        help=self.cmd_hash.__doc__)
        ap.add_argument('--search', action='store_true',
                        help=self.cmd_search.__doc__)
        ap.add_argument('--remove', action='store_true',
                        help=self.cmd_remove.__doc__)
        ap.add_argument('--cleanup', action='store_true',
                        help=self.cmd_cleanup.__doc__)
        ap.add_argument('--prune', action='store_true',
                        help=self.cmd_prune.__doc__)
        ap.add_argument('-a', '--algorithm', default=self.algorithm,
                        help='Perceptual hash algorithm. '
                             'Options: dct | mh | radial. Default: %(default)s')
        ap.add_argument('-t', '--threshold', type=float, default=self.threshold,
                        help='Minimal similarity ratio for image comparison. '
                             'Default: %(default)s%%')
        ap.add_argument('-F', '--fast', action='store_true',
                        help='Faster check for file modification '
                             '(Compare first 512 bytes only)')
        ap.add_argument('-f', '--file',
                        help='Search for duplicates of this file')
        ap.add_argument('-r', '--recursive', action='store_true',
                        help='Recursively traverse into subdirectories')
        ap.add_argument('-x', '--view', action='store_true',
                        help='View matching images (Tk GUI + %s viewer)' % self.viewer)
        ap.add_argument('--skip-bin', action='store_true',
                        help='Do not report binary equal sets')
        ap.add_argument('--db', metavar="HASHDB", default=self.dbpath,
                        help='Hash database. Default: %(default)s')
        return ap.parse_args()

    def main(self):
        args = self.process_args()
        self.algorithm = args.algorithm
        self.threshold = args.threshold
        self.dbpath = os.path.expanduser(args.db)
        path = os.path.realpath(os.path.expanduser(args.path)) \
            if args.path else None
        cmd_specified = (args.hash or args.search or args.remove or
                         args.cleanup or args.prune)
        self.load_database(must_exist=cmd_specified and not args.hash)
        # Execute commands
        if args.remove:
            self.cmd_remove(path, args.recursive)
        if args.hash:
            self.cmd_hash(path, args.recursive, args.fast)
        if args.cleanup:
            self.cmd_cleanup(path, args.fast)
        if args.prune:
            self.cmd_prune()
        if args.search:
            self.cmd_search(path, args.file, args.skip_bin, args.view)
        if not cmd_specified:
            self.cmd_hash(path, args.recursive, args.fast)
            self.cmd_cleanup(path, args.fast)
            self.cmd_search(path, args.file, args.skip_bin, args.view)

    def cmd_hash(self, path, recursive, fast_compare=False):
        """Walk through `path` and add or update image hashes in database"""
        if path:
            paths_to_hash = [path]
        else:
            paths_to_hash = [p for p in self.hashdb.list_top_paths()
                             if os.path.exists(p)]
        try:
            for path in paths_to_hash:
                for dirpath, filenames in self.list_directories(path, recursive):
                    self.update_db(dirpath, filenames, fast_compare)
        finally:
            self.save_database()

    def cmd_search(self, path, sample_file=None, skip_bin=False, view=False):
        """Search database for similar images in `path`"""
        # If path was specified, search for duplicates only in path
        # Otherwise, all hashed images in database are searched
        if path:
            self.hashdb.filter_by_path(path)
        print("Searching in %s files" % len(self.hashdb.items))
        # If sample file was specified, search for similar images
        # Otherwise, search whole database for groups of similar images
        if sample_file:
            self.compare_with_db(sample_file, view)
        else:
            try:
                if not skip_bin:
                    self.show_binary_dupes(view)
                self.search_db_for_dupes(view)
            except StopIteration:
                pass

    def cmd_remove(self, path, recursive):
        """Remove files in `path` from database"""
        def in_path(filename):
            if recursive:
                return filename.startswith(path)
            else:
                return os.path.dirname(filename) == path
        for item in self.hashdb.items:
            filtered = {fn for fn in item.file_names if not in_path(fn)}
            for removed_filename in item.file_names.difference(filtered):
                print("Removing", removed_filename)
            item.file_names = filtered
        self.save_database()

    def cmd_cleanup(self, path=None, fast=False):
        """Check files in `path`, remove references
        to deleted or modified files from the database"""
        print("Checking %s" % (path or 'database'))
        for item in self.hashdb.items:
            original_file_names = item.file_names
            item.check_file_names(path=path, fast=fast)
            for filename in original_file_names.difference(item.file_names):
                print("Removing file reference", filename)
        self.save_database()

    def cmd_prune(self):
        """Check items in database, remove those without any references to files
        (when all references were removed by --cleanup)"""
        original_items_len = len(self.hashdb.items)
        self.hashdb.prune()
        pruned = original_items_len - len(self.hashdb.items)
        if pruned:
            print("Pruned", pruned, "hashed files without any file names")
        self.save_database()

    def load_database(self, must_exist=False):
        try:
            with gzip.open(self.dbpath, 'rt', encoding='utf8') as f:
                dbitems = json.load(f)
            self.hashdb = HashDB.load(dbitems)
            print("Loaded database: %s files" % len(self.hashdb.items))
        except IOError:
            if must_exist:
                raise
            print("Could not read %r, "
                  "using new empty database..." % self.dbpath,
                  file=sys.stderr)

    def save_database(self):
        dbitems = self.hashdb.dump()
        with gzip.open(self.dbpath, 'wt', encoding='utf8') as f:
            json.dump(dbitems, f, indent='\t')

    def list_directories(self, path, recursive):
        if recursive:
            for dirpath, _dirnames, filenames in os.walk(path):
                filenames = [fname for fname in filenames
                             if self.is_image(fname)]
                filenames.sort()
                yield dirpath, filenames
        else:
            filenames = [fname for fname in os.listdir(path)
                         if self.is_image(fname)]
            filenames.sort()
            yield path, filenames

    def is_image(self, fname):
        _root, ext = os.path.splitext(fname)
        if ext.lower() in self.FORMATS:
            return True

    def update_db(self, path, filenames, fast_compare):
        print('Updating', path)
        with PoolExecutor(max_workers=os.cpu_count() or 4) as executor:
            # Compute hashes for new or updated files
            hashes = []
            imagehash_class = ImageHash.get_subclass(self.algorithm)
            for fname in filenames:
                filepath = os.path.join(path, fname)
                file_hash = self.hashdb.add(filepath, fast_compare=fast_compare)
                if self.algorithm not in file_hash.image_hash:
                    # Not seen before -> compute image hash
                    future_imghash = executor.submit(compute_hash,
                                                     imagehash_class,
                                                     filepath)
                    hashes.append((file_hash, future_imghash))
            # Write results back into HashItem objects
            for file_hash, future_imghash in hashes:
                imghash = future_imghash.result(timeout=60)
                file_hash.image_hash[self.algorithm] = imghash

    def show_binary_dupes(self, gui=False):
        """View groups of files with same binary content.

        The file names from each group are printed
        and optionally sent to the viewer.

        Raises StopIteration if quit was requested.

        """
        items = (item for item in self.hashdb.items if len(item.file_names) > 1)
        for n, item in enumerate(items, start=1):
            title = "Binary equal (set #%s)" % n
            print('--- %s ---' % title)
            for fname in item.file_names:
                print(fname)
            if gui:
                self.view(title, list(item.file_names))

    def search_db_for_dupes(self, gui=False):
        """Find and view groups of perceptually similar images.

        The file names from each group are printed
        and optionally sent to the viewer.

        Raises StopIteration if quit was requested.

        """
        threshold = 1.0 - (self.threshold / 100)
        groups = self.hashdb.find_groups(threshold, self.algorithm)
        for n, (fname_a, group) in enumerate(groups, start=1):
            title = "Perceptually similar (set #%s)" % n
            print('--- %s ---' % title)
            print(fname_a)
            file_list = [fname_a]
            for fname_b, distance in group:
                self.print_out(fname_b, distance)
                file_list.append(fname_b)
            if gui:
                self.view(title, file_list)

    def compare_with_db(self, sample_file, gui=False):
        imagehash_class = ImageHash.get_subclass(self.algorithm)
        sample_hash = imagehash_class(sample_file)
        print(sample_file)
        file_list = [sample_file]
        threshold = 1.0 - (self.threshold / 100)
        for fname, distance in self.hashdb.query(sample_hash, threshold,
                                                 self.algorithm):
            self.print_out(fname, distance)
            file_list.append(fname)
        if gui:
            self.view("Perceptually similar", file_list)

    def print_out(self, fname, distance):
        similarity = (1.0 - distance) * 100.0
        print(fname, '(%.0f%%)' % similarity)

    def view(self, title, file_list):
        """Display files from `file_list` using external program.

        Waits for external program to exit before continuing.

        Returns True if view should continue, False to stop.

        """
        from dedupimages.viewer import ViewHelper
        if not len(file_list):
            return
        title += " - dedup-images"
        print('* Opening GUI...', end='')
        sys.stdout.flush()
        try:
            want_next = ViewHelper(title, file_list, self.viewer).main()
            if not want_next:
                raise StopIteration("Quit requested")
        finally:
            print('\r' + ' ' * 30 + '\r', end='')
