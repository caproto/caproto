'''
Generate graphviz graphs from transitions in caproto._state
'''
import graphviz as gv
from collections import defaultdict
from caproto import _state as state


def to_node_name(node):
    try:
        return node.__name__
    except AttributeError:
        return repr(node)


def create_transition_graph(d, role, format_):
    graph = gv.Digraph(format=format_)
    for node in d:
        node_name = to_node_name(node)
        graph.node(node_name, label=node_name)

    self_transitions = defaultdict(lambda: [])

    for source, transitions in d.items():
        source_name = to_node_name(source)
        for received, dest in transitions.items():
            dest_name = to_node_name(dest)
            received_name = to_node_name(received)
            if source_name == dest_name:
                self_transitions[source_name].append(received_name)
                continue

            graph.edge(source_name, dest_name,
                       label=received_name)

    for node_name, received_list in self_transitions.items():
        graph.edge(node_name, node_name, label=' / '.join(received_list))
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

            filename = 'source/_static/{}_{}'.format(name, repr(role)).lower()
            print('Writing {}.{}'.format(filename, format_))

            graph.render(filename)


if __name__ == '__main__':
    generate()
