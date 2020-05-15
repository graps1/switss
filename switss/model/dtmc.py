from bidict import bidict
from graphviz import Digraph
from scipy.sparse import dok_matrix

from . import AbstractMDP
from ..utils import color_from_hash, cast_dok_matrix
from ..prism import prism

class DTMC(AbstractMDP):
    def __init__(self, P, index_by_state_action=None, label_to_states={}, **kwargs):
        """Instantiates a DTMC from a transition matrix and labelings for states.

        :param P: :math:`N \\times N` transition matrix.
        :type P: Either 2d-list, numpy.matrix, numpy.array or scipy.sparse.spmatrix
        :param label_to_states: Mapping from labels to sets of states.
        :type label_to_states: Dict[str,Set[int]]
        """# transform P into dok_matrix if neccessary
        P =  cast_dok_matrix(P)  
        assert P.shape[0] == P.shape[1], "P must be a (NxN)-matrix but has shape %s" % P.shape
        if index_by_state_action is None:
            index_by_state_action = bidict()
            for i in range(P.shape[0]):
                index_by_state_action[(i,0)] = i
        else:
            for s,a in index_by_state_action.keys():
                assert a == 0, "If state-actions are specified, DTMCs must have all 0-entries for actions: (%s,%s)" % (s,a)

        super().__init__(P, index_by_state_action, {}, label_to_states)

    def digraph(self, state_map = None, trans_map = None, action_map = None):
        """Creates a `graphviz.Digraph` object from this instance. When a digraph object is created, 
        new nodes are added for states plus additional edges for transitions between states. 
        `state_map` and `trans_map` are functions that, on some input, compute keyword arguments for
        the digraph instance. If any one of these is None, the default mapping will be used. `action_map`
        is ignored.
        
        For example, these functions below are used as default parameters if no `state_map` or `trans_map` is specified.
        
        .. highlight:: python
        .. code-block:: python

            def standard_state_map(stateidx,labels):
                return { "color" : color_from_hash(tuple(sorted(labels))),
                         "label" : "State %d\\n%s" % (stateidx,",".join(labels)),
                         "style" : "filled" }

        .. highlight:: python
        .. code-block:: python
        
            def standard_trans_map(sourceidx, destidx, p):
                return { "color" : "black", 
                         "label" : str(round(p,10)) }

        where `color_from_hash` is imported from `switss.utils`. For further information on graphviz attributes, 
        see https://www.graphviz.org/doc/info/attrs.html. 

        :param state_map: A function that computes parameters for state-nodes, defaults to None.
        :type state_map: (stateidx : int, labels : Set[str]) -> Dict[str,str], optional
        :param trans_map: A function that computes parameters for edges between actions and nodes, defaults to None. 
        :type trans_map: (sourceidx : int, destidx : int, p : float) -> Dict[str,str], optional
        :return: The digraph instance.
        :rtype: graphviz.Digraph
        """ 

        def standard_state_map(stateidx,labels):
            return { "color" : color_from_hash(tuple(sorted(labels))),
                     "label" : "State %d\n%s" % (stateidx,",".join(labels)),
                     "style" : "filled" }

        def standard_trans_map(sourceidx, destidx, p):
            return { "color" : "black", 
                     "label" : str(round(p,10)) }

        state_map = standard_state_map if state_map is None else state_map
        trans_map = standard_trans_map if trans_map is None else trans_map

        dg = Digraph()

        # connect nodes between each other
        existing_nodes = set({})

        for (rowidx, dest), p in self.P.items():
            # transition from source to dest w/ probability p
            source,_ = self.index_by_state_action.inv[rowidx]
            for node in [source, dest]:
                if node not in existing_nodes:
                    state_setting = state_map(node, self.labels_by_state[node])
                    dg.node(str(node), **state_setting)
                    existing_nodes.add(node)

            params = (source, dest, p)
            trans_setting = trans_map(*params)
            dg.edge(str(source), str(dest), **trans_setting)

        return dg

    def save(self, filepath):   
        tra_path = filepath + ".tra"
        lab_path = filepath + ".lab"

        with open(tra_path, "w") as tra_file:
            tra_file.write("%d %d\n" % (self.N, self.P.nnz))
            for (source,dest), p in self.P.items():
                tra_file.write("%d %d %f\n" % (source, dest, p))

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
        P = dok_matrix((1,1))
        N = 0

        with open(filepath) as tra_file:
            for line in tra_file:
                line_split = line.split()
                # check for first line, which has format "#states #transitions"
                if len(line_split) == 2:
                    N = int(line_split[0])
                    P.resize((N,N))
                # all other lines have format "from to prob"
                else:
                    source = int(line_split[0])
                    dest = int(line_split[1])
                    prob = float(line_split[2])
                    P[source,dest] = prob
        return { "P" :  P }
