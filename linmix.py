# What is n_k in (88), if K in (94) is number of mixture components?

import numpy as np
from astropy.table import Table
from astropy.utils.console import ProgressBar

def inv_chisqr(nu, ssqr, size=None):
    return nu * ssqr / np.random.chisquare(nu, size=size)

class LinMix(object):
    def __init__(self, x, y, xsig, ysig, K=3):
        self.x = np.array(x)
        self.y = np.array(y)
        self.xsig = np.array(xsig)
        self.ysig = np.array(ysig)
        self.N = len(self.x)
        self.K = K

    def report_all(self):
        print
        # print "xi", self.xi
        # print "eta", self.eta
        print "alpha", self.alpha
        print "beta", self.beta
        print "sigsqr", self.sigsqr
        print "pi", self.pi
        print "mu", self.mu
        print "tausqr", self.tausqr
        print "mu0", self.mu0
        print "usqr", self.usqr
        print "wsqr", self.wsqr
        # print "G", self.G

    def initial_guess(self): # Step 1
        # For convenience
        x = self.x
        y = self.y
        xsig = self.xsig
        ysig = self.ysig
        N = self.N
        K = self.K

        xvar = xsig**2
        yvar = ysig**2

        # Use BCES estimator for initial guess of theta = {alpha, beta, sigsqr}
        self.beta = np.cov(x, y, ddof=1)[1,0] / (np.var(x, ddof=1) - np.mean(xvar))
        self.alpha = np.mean(y) - self.beta * np.mean(x)
        self.sigsqr = np.var(y, ddof=1) - np.mean(yvar) - self.beta * np.cov(x, y, ddof=1)[1,0]
        self.sigsqr = np.max([self.sigsqr, 0.05 * np.var(y - self.alpha - self.beta * x,
                                                         ddof=1)])

        self.mu0 = np.median(x)
        self.wsqr = np.var(x, ddof=1) - np.median(xvar)
        self.wsqr = np.max([self.wsqr, 0.01*np.var(x, ddof=1)])

        # Now get an MCMC value dispersed around above values
        X = np.empty((N, 2), dtype=float)
        X[:,0] = 1.0
        X[:,1] = x
        Sigma = np.linalg.inv(np.dot(X.T, X)) * self.sigsqr
        coef = np.random.multivariate_normal([0, 0], Sigma)
        chisqr = np.random.chisquare(1)
        self.alpha += coef[0] * np.sqrt(1./chisqr)
        self.beta += coef[1] * np.sqrt(1./chisqr)
        self.sigsqr *= 0.5 * N / np.random.chisquare(0.5*N)

        # Now get the values for the mixture parameters, first do prior params
        self.mu0min = min(x)
        self.mu0max = max(x)
        
        success = False
        while not success:
            mu0g = self.mu0 + (np.sqrt(np.var(x, ddof=1) / N) * np.random.normal() / 
                               np.sqrt(1./np.random.chisquare(1)))
            success = (mu0g > self.mu0min) & (mu0g < self.mu0max)
        self.mu0 = mu0g

        # wsqr is the global scale
        self.wsqr *= 0.5 * N / np.random.chisquare(0.5 * N)
        
        self.umax = 1.5 * np.var(x, ddof=1)
        self.usqr = 0.5 * np.var(x, ddof=1)
        
        self.tausqr = 0.5 * self.wsqr / np.random.chisquare(4, size=K)

        self.mu = self.mu0 + np.random.normal(scale=np.sqrt(self.wsqr), size=K)
        
        # get initial group proportions and group labels
        
        pig = np.zeros(self.K, dtype=float)
        if K == 1:
            self.G = np.ones(N, dtype=int)
            self.pi = np.array([1], dtype=float)
        else:
            self.G = np.zeros((N, K), dtype=int)
            for i in xrange(N):
                minind = np.argmin(abs(x[i] - self.mu))
                pig[minind] += 1
                self.G[i,minind] = 1
            self.pi = np.random.dirichlet(pig+1)
        
        self.eta = y
        self.xi = x

    def update_xi(self): # Step 3
        # Eqn (58)
        sigma_xihat_ik_sqr_inv = np.zeros((self.N, self.K), dtype=float)
        if self.xsig is not None:
            rho_xy_sqr = 0.0
            sigma_xihat_ik_sqr_inv += 1./(self.xsig[:,np.newaxis]**2*(1-rho_xy_sqr))
        sigma_xihat_ik_sqr_inv += self.beta**2 / self.sigsqr + self.tausqr
        sigma_xihat_ik_sqr = 1./sigma_xihat_ik_sqr_inv
        # Eqn (57)
        sigma_xihat_i_sqr = np.sum(self.G * sigma_xihat_ik_sqr, axis=1)
        # Eqn (56)
        xihat_xy_i = self.x + 0
        # Eqn (55)
        xihat_ik = (sigma_xihat_i_sqr[:,np.newaxis]
                    * (0.0 + self.beta*(self.eta[:,np.newaxis] - self.alpha)/self.sigsqr
                       + self.mu/self.tausqr))
        # Eqn (54)
        xihat_i = np.sum(self.G * xihat_ik, axis=1)
        # Eqn (53)
        self.xi = np.random.normal(loc=xihat_i, scale=np.sqrt(sigma_xihat_i_sqr), size=self.N)

    def update_eta(self): # Step 4
        # Eqn (68)
        rho_xy_i = 0.0
        sigma_etahat_i_inv = 1.0 / (self.ysig**2 * rho_xy_i + 1./self.sigsqr)
        sigma_etahat_i = 1./sigma_etahat_i_inv
        # Eqn (67)
        etahat_i = sigma_etahat_i * ((self.y + 0.0) / (self.ysig**2 * (1.0 + 0.0))
                                     + (self.alpha + self.beta*self.xi)/self.sigsqr)
        # Eqn (66)
        self.eta = np.random.normal(loc=etahat_i, scale=np.sqrt(sigma_etahat_i), size=self.N)

    def update_G(self): # Step 5
        # Eqn (74)
        Np = (1./np.sqrt(2*np.pi*self.tausqr)
              * np.exp(-0.5 * (self.xi[:,np.newaxis] - self.mu)**2 / self.tausqr))
        q_ki = self.pi * Np / np.sum(self.pi * Np, axis=1)[:,np.newaxis]
        # Eqn (73)
        for i in xrange(self.N):
            self.G[i] = np.random.multinomial(1, q_ki[i])

    def update_alpha_beta(self): # Step 6
        X = np.empty((self.N, 2), dtype=float)
        X[:,0] = 1.0
        X[:,1] = self.xi
        # Eqn (77)
        tmp = np.linalg.inv(np.dot(X.T, X))
        Sigma_chat = tmp * self.sigsqr
        # Eqn (76)
        chat = np.dot(np.dot(tmp, X.T), self.eta)
        # Eqn (75)
        self.alpha, self.beta = np.random.multivariate_normal(chat, Sigma_chat)

    def update_sigsqr(self): # Step 7
        # Eqn (80)
        ssqr = 1./(self.N-2) * np.sum((self.eta - self.alpha - self.beta * self.xi)**2)
        # Eqn (79)
        nu = self.N - 2
        # Eqn (78)
        self.sigsqr = 1./inv_chisqr(nu, ssqr)

    def update_pi(self): # Step 8
        # Eqn (82)
        nk = np.sum(self.G, axis=0)
        # Eqn (81)
        self.pi = np.random.dirichlet(nk, size=1)[0]

    def update_mu(self): # Step 9
        # Eqn (86)
        Sigma_muhat_k = 1./(1./self.usqr + self.K/self.tausqr)
        # Eqn (85)
        xibar_k = 1/self.K * np.sum(self.G * self.xi[:,np.newaxis], axis=0)
        # Eqn (84)
        muhat_k = Sigma_muhat_k * (self.mu0/self.usqr + self.K/self.tausqr*xibar_k)
        # Eqn (83)
        self.mu = np.random.multivariate_normal(muhat_k, np.diag(Sigma_muhat_k))

    def update_tausqr(self): # Step 10
        # Eqn (89)
        tk_sqr = 1./(self.K+1) * np.sum(self.wsqr + self.G*(self.xi[:,np.newaxis]-self.mu)**2,
                                        axis=0)
        # Eqn (88)
        nu_k = self.K + 1
        # Eqn (87)
        self.tausqr = inv_chisqr(nu_k, tk_sqr)

    def update_mu0(self): # Step 11
        # Eqn (94)
        mubar = 1./self.K * np.sum(self.mu)
        # Eqn (93)
        self.mu0 = np.random.normal(loc=mubar, scale=np.sqrt(self.usqr/self.K), size=self.K)

    def update_usqr(self): # Step 12
        # Eqn (96)
        nu_u = self.K + 1
        # Eqn (97)
        usqrhat = 1./nu_u * (self.wsqr + np.sum((self.mu - self.mu0)**2))
        self.usqr = inv_chisqr(nu_u, usqrhat)

    def update_wsqr(self): # Step 13
        # Eqn (102)
        a = 0.5 * (self.K + 3)
        # Eqn (103)
        b = 0.5 * (1./self.usqr + np.sum(1./self.tausqr))
        # Eqn (101)
        self.wsqr = np.random.gamma(a, b)

    def step(self):
        self.update_xi()
        self.update_eta()
        self.update_G()
        self.update_alpha_beta()
        self.update_sigsqr()
        self.update_pi()
        self.update_mu()
        self.update_tausqr()
        self.update_mu0()
        self.update_usqr()
        self.update_wsqr()
        if not hasattr(self, 'chain'):
            self.chain = Table(names=['alpha', 'beta', 'sigsqr'])
        d = [self.alpha, self.beta, self.sigsqr]
        self.chain.add_row(d)

    def run_mcmc(self, niter, progress=False):
        with ProgressBar(niter) as bar:
            for i in xrange(niter):
                self.step()
                bar.update()

        return self.chain

def dump_test_data():
    print "dumping test data"
    alpha = 4.0
    beta = 3.0
    sigsqr = 0.5
    
    # GMM with 3 components for xi
    xi = np.random.normal(loc=1.0, scale=1.0, size=9)
    xi = np.concatenate([xi, np.random.normal(loc=2.0, scale=1.5, size=20)])
    xi = np.concatenate([xi, np.random.normal(loc=3.0, scale=0.5, size=30)])
    eta = 3*xi + 4
    x = xi + np.random.normal(loc=0.0, scale=0.5, size=len(xi))
    y = eta + np.random.normal(loc=0.0, scale=0.5, size=len(eta))
    xsig = np.ones_like(x) * 0.5
    ysig = np.ones_like(x) * 0.5
    
    out = Table([x, y, xsig, ysig], names=['x', 'y', 'xsig', 'ysig'])
    import astropy.io.ascii as ascii
    ascii.write(out, 'test.dat')

if __name__ == '__main__':
    import astropy.io.ascii as ascii
    try:
        a = ascii.read('test.dat')
    except:
        dump_test_data()
        a = ascii.read('test.dat')

    lm = LinMix(a['x'], a['y'], a['xsig'], a['ysig'])
    lm.initial_guess()
    lm.report_all()
    for i in range(10):
        lm.initial_guess()
        lm.report_all()