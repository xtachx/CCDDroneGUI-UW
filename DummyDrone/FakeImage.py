#!/usr/bin/env python

import numpy as np
from astropy.nddata import CCDData
import sys

data = np.random.normal(loc=0, scale=50,size=(2000,4000))
data[data<0] = 0
# data.dtype='uint32'
for iline in range(np.random.randint(4,15)):
    start, end = np.random.randint(data.shape, size=(2,2))
    while not np.all(start == end):
        data[start[0], start[1]] = np.random.randint(200, 2000)
        direction = np.sign(end-start)
        steps = ([direction[0], 0], [0, direction[1]], direction)
        start += steps[np.random.randint(0,2)]

ccd = CCDData(data=data, unit='adu')
ccd.write(sys.argv[1])


    
