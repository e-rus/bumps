"""
Estimate entropy from an MCMC state vector.

Uses probabilities computed by the MCMC sampler normalized by a scale factor
computed from the kernel density estimate at a subset of the points.\ [#Kramer]_

.. [#Kramer]
    Kramer, A., Hasenauer, J., Allgower, F., Radde, N., 2010.
    Computation of the posterior entropy in a Bayesian framework
    for parameter estimation in biological networks,
    in: 2010 IEEE International Conference on Control Applications (CCA).
    Presented at the 2010 IEEE International Conference on
    Control Applications (CCA), pp. 493-498.
    doi:10.1109/CCA.2010.5611198
"""

__all__ = ["entropy"]

from numpy import mean, std, exp, log, max, pi, e
from numpy.random import permutation
LN2 = log(2)


def scipy_stats_density(sample_points, evaluation_points):
    """
    Estimate the probability density function from which a set of sample
    points was drawn and return the estimated density at the evaluation points.
    """
    from scipy.stats import gaussian_kde

    ## standardize data so that we can use uniform bandwidth
    ## Note: this didn't help with singular matrix
    #mu, sigma = mean(data, axis=0), std(data, axis=0)
    #data,points = (data - mu)/sigma, (points - mu)/sigma

    kde = gaussian_kde(sample_points)
    return kde(evaluation_points)


def sklearn_density(sample_points, evaluation_points):
    """
    Estimate the probability density function from which a set of sample
    points was drawn and return the estimated density at the evaluation points.
    """
    from sklearn.neighbors import KernelDensity

    # Silverman bandwidth estimator
    n, d = sample_points.shape
    bandwidth = (n * (d + 2) / 4.)**(-1. / (d + 4))

    # Standardize data so that we can use uniform bandwidth.
    # Note that we will need to scale the resulting density by sigma to
    # correct the area.
    mu, sigma = mean(sample_points, axis=0), std(sample_points, axis=0)
    data, points = (sample_points - mu)/sigma, (evaluation_points - mu)/sigma

    #print("starting grid search for bandwidth over %d points"%n)
    #from sklearn.grid_search import GridSearchCV
    #from numpy import logspace
    #params = {'bandwidth': logspace(-1, 1, 20)}
    #fitter = GridSearchCV(KernelDensity(), params)
    #fitter.fit(data)
    #kde = fitter.best_estimator_
    #print("best bandwidth: {0}".format(kde.bandwidth))
    #import time; T0 = time.time()
    kde = KernelDensity(kernel='gaussian', bandwidth=bandwidth,
                        rtol=1e-6, atol=1e-6)
    #print("T:%6.3f   fitting"%(time.time()-T0))
    kde.fit(data)
    #print("T:%6.3f   estimating"%(time.time()-T0))
    log_pdf = kde.score_samples(points)
    #print("T:%6.3f   done"%(time.time()-T0))
    return exp(log_pdf)/sigma  # undo the x scaling on the data points


# scipy kde fails with singular matrix, so we will use scikit.learn
#density = scipy_stats_density
density = sklearn_density


def entropy(state, N_entropy=10000, N_norm=2500):
    r"""
    Return entropy estimate and uncertainty from an MCMC draw.

    *state* is the MCMC state vector, with sample points and log likelihoods.

    *N_norm* is the number of points $k$ to use to estimate the posterior
    density normalization factor $P(D) = \hat N$, converting
    from $\log( P(D|M) P(M) )$ to $\log( P(D|M)P(M)/P(D) )$. The relative
    uncertainty $\Delta\hat S/\hat S$ scales with $\sqrt{k}$, with the
    default *N_norm=2500* corresponding to 2% relative uncertainty.
    Computation cost is $O(nk)$ where $n$ is number of points in the draw.

    *N_entropy* is the number of points used to estimate the entropy
    $\hat S = - \int P(M|D) \log P(M|D)$ from the normalized log likelihood
    values.
    """
    # Get the sample from the state
    points, logp = state.sample()
    return _entropy(points, logp, N_entropy=N_entropy, N_norm=N_norm)

def _entropy(points, logp, N_entropy=10000, N_norm=2500):

    # Use a random subset to estimate density
    if N_norm >= len(logp):
        norm_points = points
    else:
        idx = permutation(len(points))[:N_entropy]
        norm_points = points[idx]

    # Use a different subset to estimate the scale factor between density
    # and logp.
    if N_entropy >= len(logp):
        entropy_points, eval_logp = points, logp
    else:
        idx = permutation(len(points))[:N_entropy]
        entropy_points, eval_logp = points[idx], logp[idx]

    # Normalize p to a peak probability of 1 so that exp() doesn't underflow.
    #
    # This should be okay since for the normalizing constant C:
    #
    #      u' = e^(ln u + ln C) = e^(ln u)e^(ln C) = C u
    #
    # Using eq. 11 with u' substituted for u:
    #
    #      N_est = < u'/p > = < C u/p > = C < u/p >
    #
    #      S_est = - < ln q >
    #            = - < ln (u'/N_est) >
    #            = - < ln C + ln u - ln (C <u/p>) >
    #            = - < ln u + ln C - ln C  - ln <u/p> >
    #            = - < ln u - ln <u/p> >
    #            = - < ln u > + ln <u/p>
    #
    # Uncertainty comes from eq. 13:
    #
    #      N_err^2 = 1/(k-1) sum( (u'/p - <u'/p>)^2 )
    #              = 1/(k-1) sum( (C u/p - <C u/p>)^2 )
    #              = C^2 std(u/p)^2
    #      S_err = std(u'/p) / <u'/p> = (C std(u/p))/(C <u/p>) = std(u/p)/<u/p>
    #
    # So even though the constant C shows up in N_est, N_err, it cancels
    # again when S_est, S_err is formed.
    log_scale = max(eval_logp)
    # print("max log sample: %g"%log_scale)
    eval_logp -= log_scale

    # Compute entropy and uncertainty in nats
    frac = exp(eval_logp)/density(norm_points, entropy_points)
    n_est, n_err = mean(frac), std(frac)
    s_est = (-mean(eval_logp) + log(n_est))
    s_err = n_err/n_est
    #print(n_est, n_err, s_est, s_err)
    #import pylab
    #pylab.hist(points[:,0], bins=50, normed=True)
    #idx = pylab.argsort(entropy_points[:,0])
    #pylab.plot(entropy_points[idx,0], density(norm_points, entropy_points[idx]))
    #pylab.show()

    # return entropy and uncertainty in bits
    return s_est/LN2, s_err/LN2


def _check_entropy(D):
    theta = D.rvs(size=(10000, 1))
    logp_theta = D.logpdf(theta)
    logp_theta += 27  # throw in an arbitrary scale factor
    S, Serr = _entropy(theta, logp_theta)
    print(S, Serr, D.entropy()/LN2)
    assert Serr  < 0.01
    assert abs(S - D.entropy()/LN2) < Serr

def test():
    from scipy.stats.distributions import norm as normal
    D = normal(100, 1)  # mu=100, sigma=8
    _check_entropy(D)
test.__test__ = False  # Suppress nosetests until test is fixed

if __name__ == "__main__":
    test()