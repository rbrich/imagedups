# distutils: language = c++
# distutils: libraries = pHash
# cython: language_level=3

import os

cdef extern from "pHash.h":
    ctypedef unsigned long long ulong64 "ulong64"
    int ph_dct_imagehash(char* file, ulong64 &hash)
    int ph_hamming_distance(ulong64 hasha, ulong64 hashb)


def dct_imagehash(unicode filename):
    cdef ulong64 hash = 0
    filename_enc = os.fsencode(filename)
    rc = ph_dct_imagehash(filename_enc, hash)
    if rc == -1:
        raise IOError('ph_dct_imagehash load failed')
    return hash

def hamming_distance(ulong64 hash_a, ulong64 hash_b):
    return ph_hamming_distance(hash_a, hash_b)

