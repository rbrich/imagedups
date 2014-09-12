#!/usr/bin/env python3

from imagedups.imagedups import ImageDups

prog = ImageDups()
try:
    prog.main()
except KeyboardInterrupt:
    print('Interrupted...')
