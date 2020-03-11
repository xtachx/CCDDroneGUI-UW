import numpy as np
import scipy.stats
import scipy.optimize as optimize
import matplotlib.pyplot as plt
from scipy.special import factorial
import DamicImage
from PoissonGausFit import computeGausPoissDist, paramsToList, fGausPoisson


def imageEntropy(image):
    """
	Computes the shannon information entropy (-plog(p)) of the image. Uses the pixel distribution to create the probability distribution
	Inputs:
		image - (nrows x ncolumns) 2D-numpy array (though function accepts any shape numpy array)
	Outputs:
		entropy - double of the entropy given the image pixel distribution
	"""

    # Create a histogram of the pixel values
    pixelBins = np.arange(np.min(image), np.max(image) + 1)
    pixelVals, _ = np.histogram(image.flatten(), bins=pixelBins)

    # Compute the entropy
    pixelProbabilityDistribution = pixelVals / np.sum(pixelVals)
    entropy = np.sum([-p * np.log(p) for p in pixelProbabilityDistribution if p > 0])

    return entropy


def imageEntropySlope(skImage, maxNskips=30):
    """
	Computes the rate of change of entropy as a function of the number of skips
	Inputs:
		skImage - (nrow x ncolumns x nskips) 3D numpy array
	Output:
		dSdSkips - dS/dSkips is the slope of the entropy (fit data to linear function)
	"""

    if len(skImage.shape) < 3 or skImage.shape[-1] == 1:
        return (-1, -1, -1)

    nskips = skImage.shape[2]
    nskips = np.min([nskips, maxNskips])
    singleImageEntropy = np.zeros(nskips)

    for i in range(nskips):
        singleImageEntropy[i] = imageEntropy(skImage[:, :, i])

    # Fit with linear regression
    linfunc = lambda x, *p: p[0] + p[1] * x

    paramGuess = [np.mean(singleImageEntropy), 0]
    paramFit, paramCov = optimize.curve_fit(
        linfunc, np.arange(0, nskips), singleImageEntropy, p0=paramGuess
    )

    # Return slope and uncertainy
    return paramFit[1] * 1e3, np.sqrt(np.diag(paramCov))[1] * 1e3, singleImageEntropy


def computeImageNoise(skImage, maxNskips=50):
    """
	Computes the noise of the image by fitting the zero electron peak to a gaussian
	"""

    # Figure out how many skips in the image
    if len(skImage.shape) == 2:
        nskips = 1
        skImage = np.expand_dims(skImage, 2)
    else:
        nskips = skImage.shape[-1]

    nskips = np.min([nskips, maxNskips])

    # Define gaussian fit
    gausfunc = lambda x, *p: p[0] * np.exp(-(x - p[1]) ** 2 / (2 * p[2] ** 2))

    # Iterate over each image in the skipped image, fit Guassian to the noise
    imageNoiseVec = []
    for i in range(nskips):

        # Create histogram of pixels
        med, mad = estimateDistributionParameters(skImage[:, :, i])
        bins = np.arange(med - 3 * mad, med + 3 * mad)
        y, xedges = np.histogram(skImage[:, :, i], bins=bins)
        xcenter = xedges[:-1] + np.diff(xedges)[0]

        # Perform fit
        paramGuess = [np.sum(y) / np.sqrt(2 * np.pi * mad ** 2), med, mad]
        paramOpt, _ = optimize.curve_fit(gausfunc, xcenter, y, p0=paramGuess)

        # Append to vector
        imageNoiseVec.append(paramOpt[2])

    return np.mean(imageNoiseVec)


def computeSkImageNoise(damicImage, nMovingAverage=10):
    """
	Computes the noise on single electron measurements. Takes a skipper image, searches for single electron peaks
	and fits a gaussian function to it
	Inputs:
		image - (nrows, ncolumns) 2D numpy array that we are trying to find the single electron noise of
		nMovingAverage - int, number of points to use in the smoothing moving average
	Outputs:
		skImageNoise - double, standard deviation of the gaussian fit to a single peak
		skImageNoiseErr - double, fit error of the standard deviations
	"""

    # Get histogram information
    hSkipper = damicImage.hpix
    bincSkipper = damicImage.centers

    # Find the minima and maxima
    maximaLoc, minimaLoc = findPeakPosition(
        hSkipper, bincSkipper, nMovingAverage=nMovingAverage
    )


    # Define the different fit ranges
    fitMin = []
    fitMax = []
    fitMean = []
    # Find the fit range (choose the appropriate maxima and minima)
    if maximaLoc.size > 1:
        fitDelta = np.abs(np.mean(np.diff(maximaLoc)))
    else:
        fitDelta = 2 * damicImage.mad

    for i in range(maximaLoc.size):
        # Get fit ranges for a given peak
        fitMean.append(maximaLoc[i])
        fitMax.append(maximaLoc[i] + fitDelta / 2)
        fitMin.append(maximaLoc[i] - fitDelta / 2)

    # Keep only data in the fit range
    fitIndex = (bincSkipper >= fitMin[0]) * (bincSkipper <= fitMax[0])
    fitXRange = bincSkipper[np.nonzero(fitIndex)]
    fitSkipperValues = hSkipper[np.nonzero(fitIndex)]

    # Fit peak with gaussian
    gausfunc = lambda x, *p: p[0] * np.exp(-(x - p[1]) ** 2 / (2 * p[2] ** 2))
    paramGuess = [
        hSkipper[np.nonzero(bincSkipper == fitMean[0])][0],
        fitMean[0],
        (fitMax[0] - fitMin[0]) / 6,
    ]
    try:
        paramOpt, cov = optimize.curve_fit(
            gausfunc, fitXRange, fitSkipperValues, p0=paramGuess
        )
    except (RuntimeError, optimize.OptimizeWarning, ValueError) as e:
        return -1, -1


    # Return noise and error
    skImageNoise = paramOpt[2]
    skImageNoiseErr = np.sqrt(cov[2, 2])
    return skImageNoise, skImageNoiseErr


def computeDarkCurrent(damicImage, nMovingAverage=10, nAdditionalPeaks=2):
    """
        Computes the dark current in a skipper image. Takes the integral of each peak and fits to a poisson distribution
        to get mean number of electrons per pixel per exposure.
    """

    # Get histogram information
    hSkipper = damicImage.hpix
    bincSkipper = damicImage.centers

    # Find minima and maxima
    maximaLoc, minimaLoc = findPeakPosition(
        hSkipper, bincSkipper, nMovingAverage=nMovingAverage
    )

    # Define the different fit ranges
    fitMin = []
    fitMax = []
    fitMean = []

    # Find the fit range (choose the appropriate maxima and minima)
    if maximaLoc.size > 1:
        fitDelta = np.abs(np.mean(np.diff(maximaLoc)))
    else:
        fitDelta = 2 * damicImage.mad
    for i in range(maximaLoc.size):
        # Get fit ranges for a given peak
        fitMean.append(maximaLoc[i])
        fitMax.append(maximaLoc[i] + fitDelta / 2)
        fitMin.append(maximaLoc[i] - fitDelta / 2)

    # Adds nAdditionalPeaks in case where peak finding may miss small peaks
    for i in range(nAdditionalPeaks):
        fitMean.append(fitMean[-1] + fitDelta)
        fitMax.append(fitMean[-1] + fitDelta / 2)
        fitMin.append(fitMean[-1] - fitDelta / 2)


    # Perform guass fit over all fit ranges
    gausfunc = lambda x, *p: p[0] * np.exp(-(x - p[1]) ** 2 / (2 * p[2] ** 2))
    vParam = []
    vNElectrons = []
    vNPixels = []
    nElectrons = 0
    for i in range(len(fitMean)):
        # Keep only data in the fit range
        fitIndex = (bincSkipper >= fitMin[i]) * (bincSkipper <= fitMax[i])
        fitXRange = bincSkipper[np.nonzero(fitIndex)]
        fitSkipperValues = hSkipper[np.nonzero(fitIndex)]

        paramGuess = [
            hSkipper[np.abs(bincSkipper - fitMean[i]).argmin()],
            fitMean[i],
            (fitMax[i] - fitMin[i]) / 6,
        ]

        # Perform fit
        try:
            paramOpt, cov = optimize.curve_fit(
                gausfunc, fitXRange, fitSkipperValues, p0=paramGuess
            )

            # Append results of the fit (nelectrons, fit parameters, number of pixels with that number of electrons)
            vParam.append(paramOpt)
            vNElectrons.append(nElectrons)
            vNPixels.append(paramOpt[0] * np.sqrt(2 * np.pi * paramOpt[2] ** 2))

        except:
            pass
        nElectrons += 1

    # Perform the Poisson fit to the integral
    try:
        # Add a zero number of pixels to the next electron bin
        vNElectrons.append(vNElectrons[-1] + 1)
        vNPixels.append(0)

        # Perform fit to poisson distribution
        poissonMean = np.sum([x * y for x, y in zip(vNElectrons, vNPixels)]) / np.sum(
            vNPixels
        )
        poissonfunc = lambda k, lamb: (lamb ** k / factorial(k)) * np.exp(-lamb)
        poissonParam, poissonCov = optimize.curve_fit(
            poissonfunc,
            np.array(vNElectrons),
            np.array(vNPixels) / np.sum(vNPixels),
            p0=poissonMean,
        )

    except:
        return -1, -1

    return poissonParam[0], np.sqrt(poissonCov[0][0])


def findPeakPosition(histogram, bins, nMovingAverage=10, dthresh=2):
    """
        Smooths the histogram of pixel values and searches for peaks (maxima and minima) position
    """

    # Smooth Data
    smoothCurve = np.convolve(
        histogram, np.ones(nMovingAverage) / nMovingAverage, mode="same"
    )

    # Peak find on smoothed data
    derivative = np.diff(smoothCurve)
    dthresh /= nMovingAverage
    maximaIndex = np.nonzero(
        np.hstack((0, (derivative[:-1] > dthresh) * (derivative[1:] < -dthresh), 0))
    )
    minimaIndex = np.nonzero(
        np.hstack((0, (derivative[:-1] < -dthresh) * (derivative[1:] > dthresh), 0))
    )
    maximaLoc = bins[maximaIndex]
    minimaLoc = bins[minimaIndex]

    return maximaLoc, minimaLoc


def computeImageTailRatio(damicimage, nsigma=4.0):
    """
	Calculates the ratio of the number of pixels in the left tail of the distribution to the number expected if it was
	just gaussian noise
	Inputs:
		image - (nrows, ncols, [nskips]) numpy array. Should be raw images and not the combined image
		nsigma - double, threshold definition of the tail
	Outputs:
		tailRatio - double, ratio of actual to expected number of points in the tail of the variance distribution. >> 1 is a proxy for tracks

	"""

    # Get histogram parameters
    hpix = damicimage.hpix
    bincenters = damicimage.centers
    binedges = damicimage.edges

    # Peform fit of Poisson + Gaus
    minpar = computeGausPoissDist(damicimage)
    par = paramsToList(minpar.params)

    # Expected n*sigma number of events in dist
    nGreaterThanNSigma = scipy.stats.norm.sf(nsigma) * par[4]

    # Find the x location that gives us our n sigma threshold
    gausPoisInt = lambda x: scipy.integrate.quad(fGausPoisson, x, binedges[-1], args=tuple(par))[0] - nGreaterThanNSigma
    tailLocation = scipy.optimize.fsolve(gausPoisInt, binedges[binedges.size//2])


    # Compute the ratio between the tails of the data to the fit
    tailRatio = np.sum(damicimage.image > tailLocation) / nGreaterThanNSigma

    return tailRatio


def convertValErrToString(param):
    """
		Converts a param, err tuple to string with +/- between terms
		Inputs:
			param - (val, err) combination of a given fit parameter
		Output:
			paramString - "val +/- err"
	"""
    return "%.2g +/- %.2g" % (param[0], param[1])




def histogramImage(image, nsigma=3, minRange=None):
    """
	Creates a histogram of an image (or any data set) of a reasonable range with integer (ADU) spaced bins
	Inputs:
		image - ndarray containing data values to be histogrammed
	Outputs:
		val - (nbins, ) numpy array of the histogram weights
		centers - (nbins, ) numpy  array of the bin center values
		edges - (nbins+1, ) numpy array of the bin edges
	"""

    med, mad = estimateDistributionParameters(image)

    # Create bins. +/- 3*mad
    if minRange and 2 * nsigma * mad < minRange:
        bins = np.arange(np.floor(med - minRange / 2), np.ceil(med + minRange / 2))
    else:
        bins = np.arange(np.floor(med - nsigma * mad), np.ceil(med + nsigma * mad))
    val, edges = np.histogram(image, bins=bins)
    centers = edges[:-1] + np.diff(edges)[0] / 2

    return val, centers, edges


def estimateDistributionParameters(image,):
    """
    Utility function to compute the median and mad of an image used to build the histograms. Includes a few logical checks
    regarding saturated (0 ADU) pixels
    Inputs:
        image - (n x m x k) ndarray containing pixel values. This gets flattened so the original shape does not get retained
    Outputs:
        median - double of the median value of the pixels excluding zeros (saturated)
        mad - double of the median absolute deviation of the pixels excluding zeros
    """

    if np.all(image <= 0):
        # If all pixels are saturated, median = 0, mad = 1
        return 0, 1
    else:
        med = np.median(image[image > 0])
        # Ensure that the mad is not zero
        mad = np.max(
            [scipy.stats.median_absolute_deviation(image[image > 0], axis=None), 1]
        )

    return med, mad

