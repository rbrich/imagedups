# distutils: language = c++
# distutils: libraries = pHash
# cython: language_level=3

import os
from libc.stdlib cimport free
from cphash cimport *


def dct_imagehash(str filename):
    """Compute DCT based image hash.

    Args:
        filename: String, image file name.

    Returns:
        Hash as 64bit int (8byte)

    Raises:
        IOError: Image could not be loaded from file.

    """
    filename_enc = os.fsencode(filename)
    cdef char *c_filename_enc = filename_enc
    cdef ulong64 hash = 0
    cdef int rc
    with nogil:
        rc = ph_dct_imagehash(c_filename_enc, hash)
    if rc == -1:
        raise IOError('Image load failed.')
    return hash


def hamming_distance(ulong64 hashA, ulong64 hashB):
    """Compute hamming distance between two 64bit hash values.

    Args:
        hashA. hashB: 64 bit hashes as returned from dct_imagehash.

    Returns:
        Number of differing bits.

    """
    return ph_hamming_distance(hashA, hashB)


def mh_imagehash(str filename, float alpha=2.0, float lvl=1.0):
    """Compute Marr-Hildreth operator based image hash.

    Args:
        filename: String, image file name.
        alpha: Scale factor for Marr-Hildreth operator.
        lvl: Level of the scale factor.

    Returns:
        Hash as bytes, fixed length 72.

    Raises:
        IOError: Image could not be loaded from file.

    """
    filename_enc = os.fsencode(filename)
    cdef char *c_filename_enc = filename_enc
    cdef int N = 0
    cdef uint8_t *bytearr
    with nogil:
        bytearr = ph_mh_imagehash(c_filename_enc, N, alpha, lvl)
    if bytearr == NULL:
        raise IOError('Image load failed.')
    try:
        return bytes(bytearr[:N])
    finally:
        free(bytearr)


def hamming_distance_2(bytes hashA, bytes hashB):
    """Compute normalized hamming distance between two hash values.

    Args:
        hashA. hashB: Hash strings of arbitrary, but same length.

    Returns:
        Normalized distance, float 0.0 .. 1.0

    """
    res = ph_hammingdistance2(hashA, len(hashA), hashB, len(hashB))
    if res < 0.0:
        raise ValueError('Bad hash values, must be same length.')
    return res


def radial_imagehash(str filename, float sigma=1.0, float gamma=1.0, int angles=180):
    """Compute radial variance hash.

    Args:
        filename: String, image file name.
        sigma: Deviation for the gaussian filter.
        gamma: Value for gamma correction on input image.
        angles: Number of lines to project through the center
            for 0 to 180 degrees orientation.

    Returns:
        Coefficients as bytes, fixed length 40.

    Raises:
        IOError: Image could not be loaded from file.

    """
    filename_enc = os.fsencode(filename)
    cdef char *c_filename_enc = filename_enc
    cdef Digest digest
    cdef int rc
    with nogil:
        rc = ph_image_digest(c_filename_enc, sigma, gamma, digest, angles)
    if rc == -1:
        raise IOError('Image load failed.')
    try:
        return bytes(digest.coeffs[:digest.size])
    finally:
        free(digest.coeffs)


def crosscorr(bytes hashA, bytes hashB):
    """Calculate cross correlation between two hashes.

    Args:
        hashA. hashB: Hash strings of arbitrary, but same length.

    Returns:
        Peak of cross correlation, float 0.0 .. 1.0

    """
    cdef Digest dA, dB
    cdef double pcc
    dA.coeffs = hashA
    dA.size = len(hashA)
    dB.coeffs = hashB
    dB.size = len(hashB)
    ph_crosscorr(dA, dB, pcc, 0.0)
    return pcc

