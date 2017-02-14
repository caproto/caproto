'''
Generate graphviz graphs from transitions in caproto._state
'''
import sys
import graphviz as gv
from caproto import _state as state


def to_node_name(node):
    return node.__name__


def create_transition_graph(d, role, format_):
    graph = gv.Digraph(format=format_)
    for node in d:
        node_name = to_node_name(node)
        graph.node(node_name, label=node_name)

    for source, transitions in d.items():
        source_name = to_node_name(source)
        for received, dest in transitions.items():
            dest_name = to_node_name(dest)
            graph.edge(source_name, dest_name,
                       label=to_node_name(received))

    return graph


def generate(format_='png'):
    state_dicts = dict((attr, getattr(state, attr))
                       for attr in dir(state)
                       if attr.endswith('_TRANSITIONS')
                       )


    for name, d in state_dicts.items():
        if name == 'STATE_TRIGGERED_TRANSITIONS':
            continue

        print('Creating transition graph for: ', name)
        for role in d:
            print(' - Role: ', role)
            graph = create_transition_graph(d[role], role=role,
                                            format_=format_)

            filename = '{}_{}'.format(name, role).lower()
            print('Writing {}.{}'.format(filename, format_))

            graph.render(filename)


if __name__ == '__main__':
    generate()
