"""

Calculate stability test value Lambda via discretization.

Step one is discreization of the consumption process in Schorfheide, Song and
Yaron, where log consumption growth g is given by

    g = μ + z + σ_c η'

    z' = ρ z + sqrt(1 - ρ^2) σ_z e'

    σ_z = ϕ_z σ_bar exp(h_z)

    σ_c = ϕ_c σ_bar exp(h_c)

    h_z' = ρ_hz h_z + σ_hz u'

    h_c' = ρ_hc h_c + σ_hc w'

Here {e}, {u} and {w} are IID and N(0, 1).  

The discretization method uses iterations of the Tauchen method.  The indices
are

    σ_c[k] for k in range(K)
    σ_z[i] for i in range(I)
    z[i, :] is all z states when σ_z = σ_z[i] and z[i, j] is j-th element

The discretized version is a representation of a Markov chain with finitely
many states 

    x = (σ_c, σ_z, z)

and stochastic matrix x_P giving transition probabilitites between them.

The set of states x_states is computed as a 3 x M matrix with each column
corresponding to values of (σ_c, σ_z, z)'

Discretize the SSY state process builds the discretized state values for the
    states (σ_c, σ_z, z) and a transition matrix x_P such that 

    x_P[m, mp] = probability of transition x[m] -> x[mp]

where

    x[m] := (σ_c[k], σ_z[i], z[i,j])
    
The rule for the index is

    m = k * (I * J) + i * J + j



@Stearn 
@jstac

Tue Feb 26 04:38:57 AEDT 2019

"""

from ssy_model import *
from quantecon import MarkovChain, rouwenhorst, tauchen
import numpy as np
from numpy.random import rand, randn
from numba import njit, prange

default_K, default_I, default_J = 3, 3, 3

    
def compute_spec_rad(Q):
    """
    Function to compute spectral radius of a matrix.

    """
    return np.max(np.abs(np.linalg.eigvals(Q)))

@njit
def draw_from_cdf(F):
    return np.searchsorted(F, rand())


@njit
def split_index(i, M):
    """
    A utility function for the multi-index.
    """
    div = i // M
    rem = i % M
    return (div, rem)

@njit
def single_to_multi(m, I, J):
    k, temp = split_index(m, I * J)
    i, j = split_index(temp, J)
    return (k, i, j)

@njit
def multi_to_single(k, i , j, I, J):
    return k  * (I * J) + i * J + j


class SSYConsumptionDiscretized:
    """
    A class to store the discretized version of SSY consumption dynamics.

    """

    def __init__(self,
                    ssy,
                    K,
                    I,
                    J,
                    σ_c_states,
                    σ_c_P,
                    σ_z_states,
                    σ_z_P,
                    z_states,
                    z_Q):

        self.ssy = ssy
        self.K, self.I, self.J = K, I, J
        self.σ_c_states = σ_c_states    # states
        self.σ_c_P = σ_c_P              # transition probs
        self.σ_z_states = σ_z_states    # states
        self.σ_z_P = σ_z_P              # transition probs
        self.z_states = z_states        # z[i, :] is z states when σ_z index = i
        self.z_Q = z_Q                  # z_Q[i, :, :] is trans probs when σ_z index = i
        self.x_states = None            # Optional storage for X state
        self.x_P = None                 # Optional storage for X transition probs


def discretize(ssy, K, I, J, add_x_data=False):
    """
    And here's the actual discretization process.  

    """

    ρ = ssy.ρ
    ϕ_z = ssy.ϕ_z
    σ_bar = ssy.σ_bar
    ϕ_c = ssy.ϕ_c
    ρ_hz = ssy.ρ_hz
    σ_hz = ssy.σ_hz
    ρ_hc = ssy.ρ_hc
    σ_hc = ssy.σ_hc

    hc_mc = rouwenhorst(K, 0, σ_hc, ρ_hc)
    #hc_mc = tauchen(ρ_hc, σ_hc, n=K)
    hz_mc = rouwenhorst(I, 0, σ_hz, ρ_hz)
    #hz_mc = tauchen(ρ_hz, σ_hz, n=I)

    σ_c_states = ϕ_c * σ_bar * np.exp(hc_mc.state_values)
    σ_z_states = ϕ_z * σ_bar * np.exp(hz_mc.state_values) 

    M = I * J * K
    z_states = np.zeros((I, J))
    z_Q = np.zeros((I, J, J))

    for i, σ_z in enumerate(σ_z_states):
        mc_z = rouwenhorst(J, 0, np.sqrt(1 - ρ**2) * σ_z, ρ)
        #mc_z = tauchen(ρ, np.sqrt(1 - ρ**2) * σ_z, n=J)
        for j in range(J):
            z_states[i, j] = mc_z.state_values[j]
            z_Q[i, j, :] = mc_z.P[j, :]

    # Create an instance of SSYConsumptionDiscretized to store output
    ssyd = SSYConsumptionDiscretized(ssy, 
                                    K, I, J, 
                                    σ_c_states,
                                    hc_mc.P,     # equals σ_c_P 
                                    σ_z_states,
                                    hz_mc.P,    # equals σ_z_P 
                                    z_states, 
                                    z_Q) 

    if add_x_data:
        ssyd.x_states, ssyd.x_P = build_x_mc(ssyd)

    return ssyd


def build_x_mc(ssyd):
    """
    Build the overall state process X.

    """
    σ_c_states = ssyd.σ_c_states
    σ_c_P = ssyd.σ_c_P
    σ_z_states = ssyd.σ_z_states
    σ_z_P = ssyd.σ_z_P
    z_states = ssyd.z_states
    z_Q = ssyd.z_Q
    K, I, J = ssyd.K, ssyd.I, ssyd.J

    M = I * J * K

    x_P = np.zeros((M, M))
    x_states = np.zeros((3, M))

    for m in range(M):
        k, i, j = single_to_multi(m, I, J)
        x_states[:, m] = [σ_c_states[k], σ_z_states[i], z_states[i, j]]
        for mp in range(M):
            kp, ip, jp = single_to_multi(mp, I, J)
            x_P[m, mp] = σ_c_P[k, kp] * σ_z_P[i, ip] * z_Q[i, j, jp]

    return x_states, x_P


def compute_K(ssyd):
    """
    Compute K in the SSY model.

    """

    ψ = ssyd.ssy.ψ
    γ = ssyd.ssy.γ
    β = ssyd.ssy.β

    θ = (1 - γ) / (1 - 1/ψ)
    μ_c = ssyd.ssy.μ_c
    g = 1 - γ
    K, I, J = ssyd.K, ssyd.I, ssyd.J
    M = K * I * J

    σ_c_states = ssyd.σ_c_states
    σ_z_states = ssyd.σ_z_states
    z_states = ssyd.z_states

    if ssyd.x_states is None:
        x_states, x_P = build_x_mc(ssyd)
    else: 
        x_states, x_P = ssyd.x_states, ssyd.x_P

    K_matrix = np.empty((M, M))

    for m in range(M):
        for mp in range(M):
            k, i, j = single_to_multi(m, I, J)
            σ_c, σ_z, z = σ_c_states[k], σ_z_states[i], z_states[i, j]
            a = np.exp(g * (μ_c + z) + 0.5 * g**2 * σ_c**2)
            K_matrix[m, mp] =  a * x_P[m, mp]

    return K_matrix


def test_val_spec_rad(ssy, K=default_K, I=default_I, J=default_J):
    """
    Compute the test value Lambda

    """
    ψ, γ, β = ssy.ψ, ssy.γ, ssy.β

    ssyd = discretize(ssy, K, I, J)
    K_matrix = compute_K(ssyd)
    rK = compute_spec_rad(K_matrix)
    MC = rK**(1/ (1 - γ))

    return β * MC**(1 - 1/ψ)


def mc_factory(ssy, 
                K=default_K, 
                I=default_I, 
                J=default_J, 
                parallel_flag=True):
    """
    Compute the test value Lambda via Monte Carlo, under the discretized
    consumption dynamics.

    Note that the seed currently has no effect when parallel_flag=True.

    """

    ψ = ssy.ψ
    γ = ssy.γ
    β = ssy.β
    μ_c = ssy.μ_c

    θ = (1 - γ) / (1 - 1/ψ)
    ssyd = discretize(ssy, K, I, J)

    σ_c_states = ssyd.σ_c_states
    σ_c_P_cdf = ssyd.σ_c_P.cumsum(axis=1)
    σ_z_states = ssyd.σ_z_states
    σ_z_P_cdf = ssyd.σ_z_P.cumsum(axis=1)
    z_states = ssyd.z_states

    z_Q_cdf = np.empty_like(ssyd.z_Q)
    for i in range(I):
        for j in range(J):
            z_Q_cdf[i, j, :] = ssyd.z_Q[i, j, :].cumsum()

    M = K * I * J

    # Initial state is from the middle of the state space,
    # which approximates a draw from the stationary distribution.
    # Tried drawing from the true stationary distribution and it made little
    # difference to the output and greatly increased runtime.
    k_init, i_init, j_init = K // 2, I // 2, J // 2

    @njit(parallel=parallel_flag)
    def test_val_mc(n=1000, m=1000, seed=1234):
            
        np.random.seed(seed)
        yn_vals = np.empty(m)

        for m_idx in prange(m):
            kappa_sum = 0.0
            k, i, j = k_init, i_init, j_init # single_to_multi(m_init, I, J)

            for n_idx in range(n):
                # Increment consumption
                kappa_sum += μ_c + z_states[i, j] + σ_c_states[k] * randn()
                # Update state
                j = draw_from_cdf(z_Q_cdf[i, j, :])
                k = draw_from_cdf(σ_c_P_cdf[k, :])
                i = draw_from_cdf(σ_z_P_cdf[i, :])

            yn_vals[m_idx] = np.exp((1-γ) * kappa_sum)

        mean_yns = np.mean(yn_vals)
        log_Lm = np.log(β) +  (1 / (n * θ)) * np.log(mean_yns)

        return np.exp(log_Lm)

    return test_val_mc

