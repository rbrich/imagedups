import phash
import binascii


class ImageHash:

    """ImageHash base class"""

    def __init__(self, filename=None):
        if filename:
            self.compute(filename)

    @staticmethod
    def get_subclass(algorithm):
        """Return ImageHash subclass which implements algorithm.

        Args:
            algorithm: Hash algorithm. Refers to algorithm() of ImageHash subclasses.

        """
        for cls in ImageHash.__subclasses__():
            if cls.algorithm() == algorithm:
                return cls
        raise ValueError()

    @staticmethod
    def algorithm():
        """Return string value of algorithm which is implemented by this class."""
        raise NotImplementedError()

    def compute(self, filename):
        """Compute image hash.

        Args:
            filename: Name of image file.

        Result is saved in this instance.

        """
        raise NotImplementedError()

    def load(self, hexhash):
        """Load hash value from hex string as returned by str()."""
        raise NotImplementedError()

    def distance(self, other):
        """Compute distance between this and another hash.

        Args:
            other: An instance of ImageHash.

        Returns:
            Normalized distance: 0.0 (equal) .. 1.0 (completely different)

        """
        raise NotImplementedError()


class DctImageHash(ImageHash):

    """DCT image hash algorithm"""

    def __init__(self, *args):
        self._hash = 0
        ImageHash.__init__(self, *args)

    @staticmethod
    def algorithm():
        return 'dct'

    def compute(self, filename):
        self._hash = phash.dct_imagehash(filename)

    def load(self, hexhash):
        self._hash = int(hexhash, 16)

    def distance(self, other):
        return phash.hamming_distance(self._hash, other._hash) / 64

    def __str__(self):
        return '%016X' % self._hash


class MhImageHash(ImageHash):

    """Marr-Hildreth image hash algorithm"""

    def __init__(self, *args):
        self._hash = b''
        ImageHash.__init__(self, *args)

    @staticmethod
    def algorithm():
        return 'mh'

    def compute(self, filename):
        self._hash = phash.mh_imagehash(filename)

    def load(self, hexhash):
        self._hash = binascii.unhexlify(hexhash.encode())

    def distance(self, other):
        return phash.hamming_distance_2(self._hash, other._hash)

    def __str__(self):
        return binascii.hexlify(self._hash).upper().decode()


class RadialImageHash(ImageHash):

    """Radial variance image hash algorithm"""

    def __init__(self, *args):
        self._hash = b''
        ImageHash.__init__(self, *args)

    @staticmethod
    def algorithm():
        return 'radial'

    def compute(self, filename):
        self._hash = phash.radial_imagehash(filename)

    def load(self, hexhash):
        self._hash = binascii.unhexlify(hexhash.encode())

    def distance(self, other):
        return 1.0 - phash.crosscorr(self._hash, other._hash)

    def __str__(self):
        return binascii.hexlify(self._hash).upper().decode()

