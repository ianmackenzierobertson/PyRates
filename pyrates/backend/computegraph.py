# -*- coding: utf-8 -*-
#
#
# PyRates software framework for flexible implementation of neural
# network model_templates and simulations. See also:
# https://github.com/pyrates-neuroscience/PyRates
#
# Copyright (C) 2017-2018 the original authors (Richard Gast and
# Daniel Rose), the Max-Planck-Institute for Human Cognitive Brain
# Sciences ("MPI CBS") and contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>
#
# CITATION:
#
# Richard Gast and Daniel Rose et. al. in preparation

"""This module provides the backend class that should be used to set up any backend in pyrates.
"""

# external imports
from typing import Any, Callable, Union, Iterable, Optional
from networkx import MultiDiGraph
from sympy import Symbol, Expr, Function
from copy import deepcopy
import numpy as np

# meta infos
__author__ = "Richard Gast"
__status__ = "development"


#########################
# compute graph classes #
#########################


# numpy-based node class
class ComputeNode:
    """Base class for adding variables to the compute graph. Creates a numpy array with additional attributes
    for variable identification/retrieval from graph. Should be used as parent class for custom variable classes.

    Parameters
    ----------
    name
        Full name of the variable in the original NetworkGraph (including the node and operator it belongs to).
    dtype
        Data-type of the variable. For valid data-types, check the documentation of the backend in use.
    shape
        Shape of the variable.
    """

    __slots__ = ["name", "symbol", "dtype", "shape", "_value"]

    def __init__(self, name: str, symbol: Union[Symbol, Expr, Function], dtype: Optional[str] = None,
                 shape: Optional[str] = None):
        """Instantiates a basic node of a ComputeGraph instance.
        """

        self.name = name
        self.symbol = symbol
        self.dtype = dtype
        self.shape = shape
        self._value = self._get_value(shape=shape, dtype=dtype)

    def reshape(self, shape: tuple, **kwargs):

        self._value = self.value.reshape(shape, **kwargs)
        return self

    def squeeze(self, axis=None):
        self._value = self.value.squeeze(axis=axis)
        return self

    @property
    def value(self):
        """Returns current value of BaseVar.
        """
        return self._value

    def _is_equal_to(self, v):
        for attr in self.__slots__:
            if not hasattr(v, attr) or getattr(v, attr) != getattr(self, attr):
                return False
        return True

    @staticmethod
    def _get_value(value: Optional[Union[list, np.ndarray]] = None, dtype: Optional[str] = None,
                   shape: Optional[tuple] = None):
        """Defines initial value of variable.
        """
        if value is None:
            return np.zeros(shape=shape, dtype=dtype)
        elif not hasattr(value, 'shape'):
            if type(value) is list:
                return np.asarray(value, dtype=dtype).reshape(shape)
            else:
                return np.zeros(shape=shape, dtype=dtype) + value
        elif shape:
            if value.shape == shape:
                return value
            elif sum(shape) < sum(value.shape):
                return value.squeeze()
            else:
                idx = ",".join("None" if s == 1 else ":" for s in shape)
                return eval(f'value[{idx}]')
        else:
            return np.asarray(value, dtype=dtype)

    def __deepcopy__(self, memodict: dict):
        node = ComputeNode(name=self.name, symbol=self.symbol, dtype=self.dtype, shape=self.shape)
        node._value = node._value[:]
        return node

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(str(self))


class ComputeVar(ComputeNode):
    """Class for variables and vector-valued constants in the ComputeGraph.
    """

    __slots__ = ComputeNode.__slots__ + ["vtype"]

    def __init__(self, name: str, symbol: Union[Symbol, Expr, Function], vtype: str, dtype: Optional[str] = None,
                 shape: Optional[str] = None, value: Optional[Union[list, np.ndarray]] = None):

        # set attributes
        super().__init__(name=name, symbol=symbol, dtype=dtype, shape=shape)
        self.vtype = vtype

        # adjust variable value
        self._value = self._get_value(value=value, shape=shape, dtype=dtype)


class ComputeOp(ComputeNode):
    """Class for ComputeGraph nodes that represent mathematical operations.
    """

    __slots__ = ComputeNode.__slots__ + ["func", "expr"]

    def __init__(self, name: str, symbol: Union[Symbol, Expr, Function], func: Callable, expr: Expr,
                 dtype: Optional[str] = None, shape: Optional[str] = None):

        # set attributes
        super().__init__(name=name, symbol=symbol, dtype=dtype, shape=shape)
        self.func = func
        self.expr = expr


# networkx-based graph class
class ComputeGraph(MultiDiGraph):
    """Creates a compute graph where nodes are all constants and variables of the network and edges are the mathematical
    operations linking those variables/constants together to form equations.
    """

    def __init__(self, backend: str, **kwargs):

        super().__init__()

        # choose a backend
        if backend == 'tensorflow':
            from pyrates.backend.tensorflow_backend import TensorflowBackend
            backend = TensorflowBackend
        elif backend == 'fortran':
            from pyrates.backend.fortran_backend import FortranBackend
            backend = FortranBackend
        elif backend == 'PyAuto' or backend == 'pyauto':
            from pyrates.backend.fortran_backend import PyAutoBackend
            backend = PyAutoBackend
        else:
            from pyrates.backend.base_backend import BaseBackend
            backend = BaseBackend

        # set attributes
        self.backend = backend(**kwargs)
        self.var_updates = {'DEs': dict(), 'non-DEs': dict()}
        self._eq_nodes = []

    def add_var(self, label: str, value: Any, vtype: str, **kwargs):

        unique_label = self._generate_unique_label(label)
        var = ComputeVar(name=unique_label, symbol=Symbol(unique_label), value=value, vtype=vtype, **kwargs)
        super().add_node(unique_label, node=var)
        return unique_label, self.nodes[unique_label]['node']

    def add_op(self, inputs: Union[list, tuple], label: str, expr: Expr, func: Callable, **kwargs):

        # add target node that contains result of operation
        unique_label = self._generate_unique_label(label)
        op = ComputeOp(name=unique_label, symbol=Symbol(unique_label), func=func, expr=expr, **kwargs)
        super().add_node(unique_label, node=op)

        # add edges from source nodes to target node
        for i, v in enumerate(inputs):
            super().add_edge(v, unique_label, key=i)

        return unique_label, self.nodes[unique_label]['node']

    def add_var_update(self, var: str, update: str, differential_equation: bool = False):

        # store mapping between left-hand side variable and right-hand side update
        if differential_equation:
            self.var_updates['DEs'][var] = update
        else:
            self.var_updates['non-DEs'][var] = update

        # remember var and update node to ensure that they are not pruned during compilation
        self._eq_nodes.extend([var, update])

    def eval_graph(self):

        for n in self.var_updates['non-DEs'].values():
            self.eval_subgraph(n)
        return self.eval_nodes(self.var_updates['DEs'].values())

    def eval_nodes(self, nodes: Iterable):

        return [self.eval_node(n) for n in nodes]

    def eval_node(self, n):

        inputs = [self.eval_node(inp) for inp in self.predecessors(n)]
        if 'func' in self.nodes[n]:
            return self.nodes[n]['func'](*tuple(inputs))
        return self.nodes[n]['value']

    def eval_subgraph(self, n):

        inputs = []
        input_nodes = [node for node in self.predecessors(n)]
        for inp in input_nodes:
            inputs.append(self.eval_subgraph(inp))
            self.remove_node(inp)

        node = self.nodes[n]
        if inputs:
            node['value'] = node['func'](*tuple(inputs))

        return node['value']

    def remove_subgraph(self, n):

        for inp in self.predecessors(n):
            self.remove_subgraph(inp)
        self.remove_node(n)

    def compile(self):

        # evaluate constant-based operations
        out_nodes = [node for node, out_degree in self.out_degree if out_degree == 0]
        for node in out_nodes:

            # process inputs of node
            for inp in self.predecessors(node):
                if self.nodes[inp]['vtype'] == 'constant':
                    self.eval_subgraph(inp)

            # evaluate node if all its inputs are constants
            if all([self.nodes[inp]['vtype'] == 'constant' for inp in G.predecessors(node)]):
                self.eval_subgraph(node)

        # remove unconnected nodes and constants from graph
        self._prune()

        return self

    def to_func(self, func_name: str, file_name: str, **kwargs):

        # finalize compute graph
        self.compile()

        # create state variable vector and state variable update vector
        ###############################################################

        variables, indices, updates, old_state_vars = [], [], [], []
        idx = 0
        for var, update in self.var_updates['DEs'].items():

            # extract left-hand side and right-hand side nodes from graph
            lhs, rhs = self._process_var_update(var, update)
            variables.append(lhs), updates.append(rhs)

            # store information of the original, non-vectorized state variable
            old_state_vars.append(var)
            indices.append((idx, idx+lhs.shape) if lhs.shape > 1 else idx)
            idx += lhs.shape

        # add vectorized state variables and updates to the backend
        state_vec = self.ops['concat']['func'](variables, axis=0)
        state_var_key, y = self.add_var(label='y', vtype='state_var', value=state_vec)
        rhs_var_key, dy = self.add_var(label='dy', vtype='state_var', value=np.zeros_like(state_vec))

        # create a string containing all computations and variable updates represented by the compute graph
        func_args, code_gen = self._to_str(state_vec_indices=indices)
        func_body = code_gen.generate()
        code_gen.clear()

        # generate function head
        # TODO: move function generation methods to compute graph
        func_args, code_gen = self._generate_func_head(func_name=func_name, code_gen=code_gen,
                                                       state_var=state_var_key, func_args=func_args,
                                                       imports=self.backend.imports)

        # add lines from function body after function head
        code_gen.add_linebreak()
        code_gen.add_code_line(func_body)
        code_gen.add_linebreak()

        #
        #         # generate function tail
        #         code_gen = self._generate_func_tail(code_gen=code_gen, rhs_var=rhs_var_key)
        #
        #         # finalize function string
        #         func_str = code_gen.generate()
        #
        #         # write function string to file
        #         func = self._generate_func(func_str, func_name=func_name, file_name=file_name, build_dir=self._build_dir,
        #                                    **kwargs)
        #         return_dict['func'] = func
        #         return_dict['func_args'] = func_args

    def _to_str(self, state_vec_indices: list):

        # preparations
        code_gen = self.backend
        backend_funcs = {key: val['str'] for key, val in self.ops.items()}

        # extract state variable from state vector
        rhs_indices_str = []
        for idx, var in zip(state_vec_indices, self.var_updates['DEs']):

            # turn index to string
            idx_str = f'{idx}' if type(idx) is int else f'{idx[0]}:{idx[1]}'

            # extract state variable from state vector
            code_gen.add_code_line(f"{var} = y{code_gen.create_index_str(idx_str)}")
            rhs_indices_str.append(idx_str)

        code_gen.add_linebreak()

        # get equation string and argument list for each non-DE node at the end of the compute graph hierarchy
        func_args2, delete_args1, code_gen = self._generate_update_equations(code_gen,
                                                                             differential_equations=False,
                                                                             funcs=backend_funcs)
        code_gen.add_linebreak()

        # get equation string and argument list for each DE node at the end of the compute graph hierarchy
        func_args1, delete_args2, code_gen = self._generate_update_equations(code_gen,
                                                                             differential_equations=True,
                                                                             funcs=backend_funcs)

        # remove unnecessary function arguments
        func_args = func_args1 + func_args2
        for arg in delete_args1 + delete_args2:
            while arg in func_args:
                func_args.pop(func_args.index(arg))

        return func_args, code_gen

    def _generate_update_equations(self, code_gen, differential_equations: bool, funcs: dict = None,
                                   indices: list = None):

        # collect right-hand side expression and all input variables to these expressions
        nodes = self.graph.var_updates['DEs' if differential_equations else 'non-DEs']
        func_args, expressions, var_names, defined_vars = [], [], [], []
        for node, update in nodes.items():

            # collect expression and variables of right-hand side of equation
            expr_args, expr = self.graph.node_to_expr(update, **funcs)
            func_args.extend(expr_args)
            expressions.append(self.backend.expr_to_str(expr))

            # process left-hand side of equation
            var = self.get_var(node)
            if 'expr' in var:
                # process indexing of left-hand side variable
                idx_args, lhs = self.graph.node_to_expr(node, **funcs)
                func_args.extend(idx_args)
                lhs_var = self.backend.expr_to_str(lhs)
            else:
                # process normal update of left-hand side variable
                lhs_var = var['symbol'].name
            var_names.append(lhs_var)

        # add the left-hand side assignments of the collected right-hand side expressions to the code generator
        if differential_equations:

            # differential equation (DE) update
            if not indices:
                raise ValueError('State variables need to be stored in a single state vector, for which the indices '
                                 'have to be passed to this method.')

            # DE updates stored in a state-vector
            for idx, expr in zip(indices, expressions):
                code_gen.add_code_line(f"dy{code_gen.create_index_str(idx)} = {expr}")

            # add rhs var to function arguments
            func_args = ['dy'] + func_args

        else:

            # TODO: implement graph-based method for getting the order of the non-DEs right.
            # non-differential equation update
            var_names, expressions, undefined_vars, defined_vars = sort_equations(var_names, expressions)
            func_args.extend(undefined_vars)

            if indices:
                raise ValueError('Indices to non-state variables should be defined in the respective equations, not'
                                 'be passed to this method.')

            # non-DE update stored in a single variable
            for target_var, expr in zip(var_names, expressions):
                code_gen.add_code_line(f"{target_var} = {expr}")

        return func_args, defined_vars, code_gen

    def _node_to_expr(self, n: str, **kwargs) -> tuple:

        # TODO: Improve this method as much as possible

        expr_args = []
        try:
            expr = self.nodes[n]['expr']
            expr_info = {self.nodes[inp]['symbol']: self._node_to_expr(inp, **kwargs) for inp in self.predecessors(n)}
            for expr_old, (args, expr_new) in expr_info.items():
                expr = expr.replace(expr_old, expr_new)
                expr_args.extend(args)
            # TODO: check beforehand, whether next step is necessary (e.g. indicate existence of undefined functions)
            for expr_old, expr_new in kwargs.items():
                expr = expr.replace(Function(expr_old), Function(expr_new))
            return expr_args, expr
        except KeyError:
            if self.nodes[n]['vtype'] in ['constant', 'input']:
                expr_args.append(n)
            return expr_args, self.nodes[n]['symbol']

    def _process_var_update(self, var: str, update: str) -> tuple:

        # extract nodes
        lhs = self.get_var(var)
        rhs = self.graph.eval_node(update)

        # extract common shape
        if not lhs.shape:
            lhs.reshape((1,))
        if not rhs.shape:
            rhs = np.reshape(rhs, (1,))
        if lhs.shape == rhs.shape:
            return lhs, rhs
        raise ValueError(
            f"Shapes of state variable {var} and its right-hand side update {rhs.expr} do not"
            " match.")

    def _prune(self):

        # remove all subgraphs that contain constants only
        for n in [node for node, out_degree in self.out_degree if out_degree == 0]:
            if self.nodes[n]['vtype'] == 'constant' and n not in self._eq_nodes:
                self.remove_subgraph(n)

        # remove all unconnected nodes
        for n in [node for node, out_degree in self.out_degree if out_degree == 0]:
            if self.in_degree(n) == 0 and n not in self._eq_nodes:
                self.remove_node(n)

    def _generate_unique_label(self, label: str):

        if label in self.nodes:
            label_split = label.split('_')
            try:
                new_label = "_".join(label_split[:-1] + [f"{int(label_split[-1])+1}"])
            except ValueError:
                new_label = f"{label}_0"
            return self._generate_unique_label(new_label)
        else:
            return label

    def get_var(self, var: str):
        return self.nodes[var]['node']

    @property
    def ops(self):
        return self.backend.ops

    @property
    def dtypes(self):
        return self.backend.dtypes
