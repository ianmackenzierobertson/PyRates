# pyrates _imports
from pyrates.ir.circuit import CircuitIR
from pyrates.frontend import CircuitTemplate

# additional _imports
import numpy as np
from pandas import DataFrame
from copy import deepcopy
import os
import tensorflow as tf
from numba import njit, config

# threading configs
config.THREADING_LAYER = 'tbb'
os.environ["KMP_BLOCKTIME"] = '0'
os.environ["KMP_SETTINGS"] = 'true'
os.environ["KMP_AFFINITY"] = 'granularity=fine,verbose,compact,1,0'
os.environ["OMP_NUM_THREADS"] = '2'
tf.config.threading.set_inter_op_parallelism_threads(4)
tf.config.threading.set_intra_op_parallelism_threads(2)
tf.config.optimizer.set_jit(True)
# tf.config.experimental.set_synchronous_execution(False)
#tf.debugging.set_log_device_placement(True)


def benchmark(Ns, Ps, T, dt, init_kwargs, run_kwargs, disable_gpu=False):
    """Function that will run a benchmark simulation for each combination of N and P.
    Each benchmark simulation simulates the behavior of a neural population network, where the Jansen-Rit model is used for each of the N nodes and
    connections are drawn randomly, such that on overall coupling density of P is established.

    Parameters
    ----------
    Ns
        Vector with network sizes.
    Ps
        Vector with coupling densities.
    T
        Overall simulation time.
    dt
        Integration step-size.
    init_kwargs
        Additional key-word arguments for the model initialization.
    run_kwargs
        Additional key-word arguments for running the simulation.
    disable_gpu
        If true, GPU devices will be disabled, so the benchmark will be run on the CPU only.

    Returns
    -------
    tuple
        Simulation times, peak memory consumptions

    """

    if disable_gpu:
        os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
    else:
        os.environ['CUDA_VISIBLE_DEVICES'] = '0'

    times = np.zeros((len(Ns), len(Ps)))

    for i, n in enumerate(Ns):
        for j, p in enumerate(Ps):

            print(f'Running benchmark for n = {n} and p = {p}.')
            print("Setting up the network in PyRates...")

            # define inter-JRC connectivity
            C = np.random.uniform(size=(n, n))
            C[C > p] = 0.
            c_sum = np.sum(C, axis=1)
            for k in range(C.shape[0]):
                if c_sum[k] != 0.:
                    C[k, :] /= c_sum[k]

            # define input
            inp = 220 + np.random.randn(int(T / dt), n) * 22.

            # set up network representation
            circuit = CircuitIR()
            for idx in range(n):
                circuit.add_circuit(f'jrc_{idx}', CircuitIR.from_yaml("model_templates.jansen_rit.simple_jansenrit.JRC")
                                    )
            circuit.add_edges_from_matrix(source_var="PRO/m_out", target_var="RPO_e_pc/m_in",
                                          nodes=[f'jrc_{idx}/PC' for idx in range(n)], weight=C)

            # set up compute graph
            net = circuit.compile(dt=dt, **init_kwargs)

            print("Starting the benchmark simulation...")

            # run simulations
            _, t = net.run(T, inputs={'all/PC/RPO_e_pc/u': inp}, outputs={'V': 'all/PC/RPO_e_pc/PSP'}, verbose=False,
                           **run_kwargs)
            times[i, j] = t

            print("Finished!")
            print(f'simulation time: {t} s.')

    return times


# define parameters and functions
dt = 1e-4                                       # integration step-size of the forward euler solver in s
T = 1.0                                         # simulation time in s
c = 1.                                          # global connection strength scaling
N = np.round(2**np.arange(12))[::-1]            # network sizes, each of which will be run a benchmark for
p = np.linspace(0.64, 0.65, 2)                  # global coupling probabilities to run benchmarks for
use_gpu = False                                 # if false, benchmarks will be run on CPU
n_reps = 1                                      # number of trials per benchmark

# simulate benchmarks
results = np.zeros((len(N), len(p), n_reps))                                # array in which results will be stored
for i in range(n_reps):
    print(f'Starting benchmark simulation run # {i}...')
    t = benchmark(N, p, T, dt,
                  init_kwargs={'vectorization': True, 'backend': 'numpy', 'solver': 'euler',
                               'matrix_sparseness': 0.5},
                  run_kwargs={'profile': 't',
                              'sampling_step_size': 1e-3},
                  disable_gpu=False if use_gpu else True)                   # benchmarks simulation times and memory
    results[:, :, i] = t
    print(f'Finished benchmark simulation run # {i}!')

#np.save(f"{'gpu' if use_gpu else 'cpu'}_benchmarks", results)
#np.save('n_jrcs', N)
#np.save('conn_prob', p)
