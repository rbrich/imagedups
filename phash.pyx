# distutils: language = c++
# distutils: libraries = pHash
# cython: language_level=3

import os
from libc.stdlib cimport free


cdef extern from "pHash.h":
    ctypedef unsigned long long     ulong64 "ulong64"
    ctypedef unsigned char          uint8_t "uint8_t"

    int ph_dct_imagehash(char *filename, ulong64 &hash)
    int ph_hamming_distance(ulong64 hashA, ulong64 hashB)

    uint8_t* ph_mh_imagehash(char *filename, int &N, float alpha, float lvl)
    double ph_hammingdistance2(uint8_t *hashA, int lenA, uint8_t *hashB, int lenB)


def dct_imagehash(str filename):
    """Compute DCT based image hash.

    Args:
        filename: String, image file name.

    Returns:
        Hash as 64bit int (8byte)

    Raises:
        IOError: Image could not be loaded from file.

    """
    cdef ulong64 hash = 0
    filename_enc = os.fsencode(filename)
    rc = ph_dct_imagehash(filename_enc, hash)
    if rc == -1:
        raise IOError('Image load failed.')
    return hash


def hamming_distance(ulong64 hash_a, ulong64 hash_b):
    """Compute hamming distance between two 64bit hash values.

    """
    return ph_hamming_distance(hash_a, hash_b)


def mh_imagehash(str filename, float alpha=2.0, float lvl=1.0):
    """Compute Marr-Hildreth operator based image hash.

    Args:
        alpha: Scale factor for Marr-Hildreth operator.
        lvl: Level of the scale factor.

    Returns:
    """
    cdef int N = 0
    cdef uint8_t *bytearr
    filename_enc = os.fsencode(filename)
    bytearr = ph_mh_imagehash(filename_enc, N, alpha, lvl)
    if bytearr == NULL:
        raise IOError('Image load failed.')
    try:
        return bytes(bytearr[:N])
    finally:
        free(bytearr)


def hamming_distance_2(bytes hashA, bytes hashB):
    return ph_hammingdistance2(hashA, len(hashA), hashB, len(hashB))

