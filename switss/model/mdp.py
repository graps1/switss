from graphviz import Digraph
from scipy.sparse import dok_matrix
from bidict import bidict
from collections import defaultdict

from . import AbstractMDP
from ..prism import prism
from ..utils import color_from_hash

class MDP(AbstractMDP):
    def __init__(self, P, index_by_state_action, label_to_actions={}, label_to_states={}):
        """Instantiates a MDP from a transition matrix, a bidirectional
        mapping from state-action pairs to corresponding transition matrix entries and labelings for states and actions.

        :param P: :math:`C_{S_{\\text{all}}} \\times N_{S_{\\text{all}}}` transition matrix.
        :type P: Either 2d-list, numpy.matrix, numpy.array or scipy.sparse.spmatrix
        :param index_by_state_action: A bijection of state-action pairs :math:`(s,a) \in \mathcal{M}_{S_{\\text{all}}}` 
            to indices :math:`i=0,\dots,C_{S_{\\text{all}}}-1` and vice versa.
        :type index_by_state_action: Dict[Tuple[int,int],int]
        :param label_to_actions: Mapping from labels to sets of state-action pairs.
        :type label_to_actions: Dict[str,Set[Tuple[int,int]]]
        :param label_to_states: Mapping from labels to sets of states.
        :type label_to_states: Dict[str,Set[int]]
        """
        super().__init__(P, index_by_state_action, label_to_actions, label_to_states)


    def digraph(self, state_map = None, trans_map = None, action_map = None):      
        """
        Creates a graphviz.Digraph object from this instance. When a digraph object is created, 
        new nodes are added for states and actions plus additional edges between actions and nodes. 
        `state_map`, `trans_map` and `action_map` are functions that, on some input, compute keyword arguments for
        the digraph instance. If any one of these is None, the default mapping will be used.
        
        For example, these functions below are used as default parameters if no `state_map`, `trans_map` or `action_map` is specified.
        
        .. code-block:: python

            def standard_state_map(stateidx,labels):
                return { "style" : "filled",
                         "color" : color_from_hash(tuple(sorted(labels))),
                         "label" : "State %d\\n%s" % (stateidx,",".join(labels)) }

        .. code-block:: python

            def standard_trans_map(sourceidx, action, destidx, p):
                return { "color" : "black", 
                         "label" : str(round(p,10)) }

        .. code-block:: python

            def standard_action_map(sourceidx, action, labels):
                return { "node" : { "label" :  "%s\\n%s" % (action, "".join(labels)),
                                    "color" : "black", 
                                    "shape" : "rectangle" }, 
                         "edge" : { "color" : "black",
                                    "dir" : "none" } }

        where `color_from_hash` is imported from `switss.utils`. For further information on graphviz attributes, 
        see https://www.graphviz.org/doc/info/attrs.html. 


        :param state_map: A function that computes parameters for state-nodes, defaults to None.
        :type state_map: (stateidx : int, labels : Set[str]) -> Dict[str,str], optional
        :param trans_map: A function that computes parameters for edges between actions and nodes, defaults to None. 
        :type trans_map: (sourceidx : int, action : int, destidx : int, p : float) -> Dict[str,str], optional
        :param action_map: A function that computes parameters for action-nodes and edges between nodes and corresponding actions, defaults to None.
        :type action_map: (sourceidx : int, action : int, sourcelabels : Set[str]) -> Dict[str,Dict[str,str]], optional
        :return: The digraph instance.
        :rtype: graphviz.Digraph
        """ 

        def standard_state_map(stateidx,labels):
            return { "style" : "filled",
                     "color" : color_from_hash(tuple(sorted(labels))),
                     "label" : "State %d\n%s" % (stateidx,",".join(labels)) }

        def standard_trans_map(sourceidx, action, destidx, p):
            return { "color" : "black", 
                     "label" : str(round(p,10)) }

        def standard_action_map(sourceidx, action, labels):
            return { "node" : { "label" :  "%s\n%s" % (action, "".join(labels)),
                                "color" : "black", 
                                "shape" : "rectangle" }, 
                     "edge" : { "color" : "black",
                                "dir" : "none" } }

        state_map = standard_state_map if state_map is None else state_map
        trans_map = standard_trans_map if trans_map is None else trans_map
        action_map = standard_action_map if action_map is None else action_map

        dg = Digraph()

        # connect nodes between each other
        existing_nodes = set({})
        existing_state_action_pairs = set({})

        for (idx, dest), p in self.P.items():
            source, action = self.index_by_state_action.inv[idx]

            # transition from source to dest w/ probability p
            for node in [source, dest]:
                if node not in existing_nodes:
                    state_setting = state_map(node, self.labels_by_state[node])
                    dg.node(str(node), **state_setting)
                    existing_nodes.add(node)

            params_trans = (source, action, dest, p)
            trans_setting = trans_map(*params_trans)
            params_action = (source, action, self.labels_by_action[(source,action)])
            action_setting = action_map(*params_action)
            action_node_name = "%s-%s" % (source,action)

            if idx not in existing_state_action_pairs:
                existing_state_action_pairs.add(idx)
                dg.node(action_node_name, **action_setting["node"])
                dg.edge(str(source), action_node_name, **action_setting["edge"])

            dg.edge(action_node_name, str(dest), **trans_setting)
                
        return dg

    def save(self, filepath):
        tra_path = filepath + ".tra"
        lab_path = filepath + ".lab"

        with open(tra_path, "w") as tra_file:
            tra_file.write("%d %d %d\n" % (self.N, self.C, self.P.nnz))
            for (index,dest), p in self.P.items():
                if p > 0:
                    source,action = self.index_by_state_action.inv[index]
                    tra_file.write("%d %d %d %f\n" % (source, action, dest, p))

        with open(lab_path, "w") as lab_file:
            unique_labels_list = list(self.states_by_label.keys())
            header = ["%d=\"%s\"" % (i, label) for i,label in enumerate(unique_labels_list)]
            lab_file.write("%s\n" % (" ".join(header)))
            for idx, labels in self.labels_by_state.items():
                if len(labels) == 0:
                    continue
                labels_str = " ".join(map(str, map(unique_labels_list.index, labels)))
                lab_file.write("%d: %s\n" % (idx, labels_str))

        return tra_path, lab_path

    @classmethod
    def _load_transition_matrix(cls, filepath):
        """Loads a transition matrix from a .tra-file
        
        :param tra_file_path: filepath to .tra-file
        :type tra_file_path: str
        :return: a bidict that contains mappings from state-action pairs to an index set :math:`\{0,\dots,C\}` and a transition matrix  
        :rtype: Tuple[scipy.sparse.dok_matrix, bidict.bidict]
        """
        P = dok_matrix((1,1))
        index_by_state_action = bidict()
        label_to_actions = defaultdict(set)

        with open(filepath,"r") as tra_file:
            # the first line should have format "#states #choices #transitions"
            # the number of choices is the number of active state-action pairs
            first_line_split = tra_file.readline().split()
            N = int(first_line_split[0])
            C = int(first_line_split[1])
            P.resize((C,N))

            max_index = 0
            for line in tra_file.readlines():
                # all other lines have format "source action dest prob"
                line_split = line.split()
                source = int(line_split[0])
                action = int(line_split[1])
                dest = int(line_split[2])
                prob = float(line_split[3])
                if len(line_split) == 5:
                    actionlabel = line_split[4]
                    label_to_actions[actionlabel].add((source,action))

                if (source,action) in index_by_state_action:
                    index = index_by_state_action[(source,action)]
                else:
                    index = max_index
                    index_by_state_action[(source,action)] = max_index
                    max_index += 1
                P[index,dest] = prob

        return { "P" : P, "index_by_state_action" : index_by_state_action, "label_to_actions" : label_to_actions }
