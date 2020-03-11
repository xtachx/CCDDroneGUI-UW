#!/usr/bin/env python3

import numpy as np
from astropy.nddata import CCDData
import sys
import matplotlib.pyplot as plt

sys.path.append("../analysis")
import PoissonGausFit as poisgaus 
from scipy.stats import rv_continuous
import scipy

class PoissonGausDistribution(rv_continuous):
	"""docstring for PoissonGausDistribution"""
	def __init__(self, arg):
		super(PoissonGausDistribution, self).__init__()
		self.arg = arg

	def _pdf(self, x):
		return poisgaus.fGausPoisson(x, *self.arg)

	def _cdf(self, x):
		return poisgaus.fCDFGausPoisson(x, *self.arg)

	def rvs(self, size=1):
		return np.random.normal(0, self.arg[0], size=size) + self.arg[3] * np.random.poisson(self.arg[1], size=size) + self.arg[2] 


# Define parameters to draw from
# par = [sigma, lambda, offset, ADU conv, scaling, npoiss terms]
par = [np.random.uniform(1, 2), np.random.uniform(0, 0.7), 20, np.random.uniform(8, 12), 1, 10]
poisGausRV = PoissonGausDistribution(par)


# Generate data
data = poisGausRV.rvs(size=(2000,4000))

# Save as "CCD image"
ccd = CCDData(data=data, unit='adu')
ccd.write(sys.argv[1])


    
