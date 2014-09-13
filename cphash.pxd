cdef extern from "pHash.h" nogil:
    ctypedef unsigned long long     ulong64 "ulong64"
    ctypedef unsigned char          uint8_t "uint8_t"
    ctypedef struct Digest:
        char *id
        uint8_t *coeffs
        int size

    # DCT
    int ph_dct_imagehash(char *filename, ulong64 &hash)
    int ph_hamming_distance(ulong64 hashA, ulong64 hashB)

    # Marr-Hildreth
    uint8_t* ph_mh_imagehash(char *filename, int &N, float alpha, float lvl)
    double ph_hammingdistance2(uint8_t *hashA, int lenA, uint8_t *hashB, int lenB)

    # Radial Variance
    int ph_image_digest(char *file, double sigma, double gamma, Digest &digest, int N)
    int ph_crosscorr(Digest &x, Digest &y, double &pcc, double threshold)
