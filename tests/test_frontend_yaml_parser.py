
# -*- coding: utf-8 -*-
#
#
# PyRates software framework for flexible implementation of neural 
# network models and simulations. See also: 
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
""" Tests for the parser that translates circuits and components defined in YAML into the intermediate
python representation.
"""

__author__ = "Daniel Rose"
__status__ = "Development"

import pytest


def setup_module():
    print("\n")
    print("===========================")
    print("| Test Suite: YAML Parser |")
    print("===========================")


@pytest.mark.parametrize("operator", ["model_templates.jansen_rit.axon.axon.PotentialToRateOperator",
                                      "model_templates.jansen_rit.axon.templates.SigmoidPRO",
                                      "model_templates.jansen_rit.axon.templates.JansenRitPRO",
                                      "model_templates.jansen_rit.population.population.CurrentToPotentialOperator",
                                      "model_templates.jansen_rit.synapse.synapse.RateToCurrentOperator"
                                      ])
def test_import_operator_templates(operator):
    """test basic (vanilla) YAML parsing using ruamel.yaml (for YAML 1.2 support)"""
    from pyrates.frontend.template.operator import OperatorTemplate
    from pyrates.frontend.template import template_cache, clear_cache
    clear_cache()

    template = OperatorTemplate.from_yaml(operator)  # type: OperatorTemplate

    assert template.path in template_cache

    cached_template = template_cache[operator]  # type: OperatorTemplate
    assert template is cached_template
    assert template.path == cached_template.path
    assert template.equations == cached_template.equations
    assert repr(template) == repr(cached_template) == f"<OperatorTemplate '{operator}'>"


def test_full_jansen_rit_circuit_template_load():
    """Test a simple circuit template, including all nodes, edges and operators to be loaded."""

    path = "model_templates.jansen_rit.circuit.JansenRitCircuit"
    from pyrates.frontend.template.circuit import CircuitTemplate
    from pyrates.frontend.template.edge import EdgeTemplate
    from pyrates.frontend.template.node import NodeTemplate
    from pyrates.frontend.template.operator import OperatorTemplate
    from pyrates.frontend.template import template_cache, clear_cache
    clear_cache()

    template = CircuitTemplate.from_yaml(path)

    # test, whether circuit is in loader cache
    assert template is template_cache[path]

    # test, whether node templates have been loaded successfully
    nodes = {"JR_PC": "model_templates.jansen_rit.population.templates.JansenRitPC",
             "JR_IIN": "model_templates.jansen_rit.population.templates.JansenRitIN",
             "JR_EIN": "model_templates.jansen_rit.population.templates.JansenRitIN"}

    for key, value in nodes.items():
        assert isinstance(template.nodes[key], NodeTemplate)
        assert template.nodes[key] is template_cache[value]
        # test operators in node templates
        for op in template.nodes[key].operators:
            assert op.path in template_cache
            assert isinstance(op, OperatorTemplate)

    # test, whether coupling operator has been loaded correctly
    coupling_path = "model_templates.jansen_rit.edges.LinearCouplingOperator"
    edge_temp = template.edges[0][2]
    assert isinstance(edge_temp, EdgeTemplate)
    assert list(edge_temp.operators)[0] is template_cache[coupling_path]
    assert repr(template) == f"<CircuitTemplate '{path}'>"


def test_circuit_instantiation():
    """Test, if apply() functions all work properly"""
    path = "model_templates.jansen_rit.circuit.JansenRitCircuit"
    from pyrates.frontend import template, clear_frontend_caches
    clear_frontend_caches()

    circuit_template = template.from_yaml(path)

    circuit = circuit_template.apply()[0]

    # test whether edge operator has been added as a network node
    assert 'LCEdge' in circuit.nodes
    assert circuit['LCEdge']['LinearCouplingOperator']['variables']['c']['shape'] == (4,)

    # test whether edge operator is properly connected with network
    assert circuit.edges[('LCEdge', 'JR_PC', 0)]
    assert circuit.edges[('LCEdge', 'JR_PC', 1)]
    assert len(circuit.edges[('LCEdge', 'JR_IIN', 0)]['target_idx']) == 2
    assert circuit.edges[('JR_IIN', 'LCEdge', 0)]
    assert circuit.edges[('JR_IIN', 'LCEdge', 1)]
    assert len(circuit.edges[('JR_PC', 'LCEdge', 0)]['target_idx']) == 2

    # now test, if JR_EIN and JR_IIN have been vectorized into a single operator graph
    assert len(circuit["JR_IIN"]['JansenRitPRO']['variables']['m_out']['value']) == 2

    # now test, if the references are collected properly
    for node in circuit_template.nodes:
        if node in circuit_template._ir_map:
            node = circuit_template._ir_map[node]
        assert node in circuit
    circuit_template.clear()

    # verify that .apply also understands value updates to nodes
    value_dict = {"JR_PC/JansenRitExcitatorySynapseRCO/h": 0.1234}
    clear_frontend_caches()
    circuit_template = template.from_yaml(path)
    circuit2 = circuit_template.apply(node_values=value_dict)[0]
    var = circuit2["JR_PC"]["JansenRitExcitatorySynapseRCO"]['variables']['h']
    circuit_template.clear()
    assert float(var['value']) - 0.1234 == pytest.approx(0, rel=1e-4, abs=1e-4)


@pytest.mark.skip
def test_multi_circuit_instantiation():
    """Test, if a circuit with subcircuits is also working."""
    path = "model_templates.jansen_rit.circuit.MultiJansenRitCircuit"
    from pyrates.frontend import template as tpl
    tpl.clear_cache()

    template = tpl.from_yaml(path)

    circuit = template.apply()
    assert circuit


def test_equation_alteration():
    """Test, if properties of a template that mean to alter a certain parent equation are treated correctly"""

    path = "model_templates.jansen_rit.population.templates.InstantaneousCPO"
    # this template removes the component "L_m * " from the base equation "L_m * V = k * I"
    from pyrates.frontend.template.operator import OperatorTemplate

    template = OperatorTemplate.from_yaml(path)

    operator, _ = template.apply()

    assert operator.equations == ("V = k * I_0",)


# ToDo: implement to_dict methods on template classes
@pytest.mark.skip
def test_yaml_dump():
    """Test the functionality to dump an object to YAML"""
    from pyrates.frontend import fileio, clear_frontend_caches

    with pytest.raises(AttributeError):
        fileio.save("no_to_dict()", "random_art", "yaml")

    from pyrates.frontend.template.circuit import CircuitTemplate
    clear_frontend_caches()
    circuit = CircuitTemplate.from_yaml("model_templates.jansen_rit.circuit.JansenRitCircuit")

    with pytest.raises(ValueError):
        fileio.save(circuit, "output/yaml_dump.yaml", "yml")

    with pytest.raises(TypeError):
        fileio.save(circuit, "output/yaml_dump.yaml", "yaml")

    fileio.save(circuit, "output/yaml_dump.yaml", "yaml", "DumpedCircuit")

    # reload saved circuit
    circuit.clear()
    clear_frontend_caches()
    saved_circuit = CircuitTemplate.from_yaml("output/yaml_dump/DumpedCircuit"
                                              ).apply(step_size=1e-3)[0]
    assert saved_circuit
