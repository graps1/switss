#cython: language_level=3

from libc.stdlib cimport malloc, free
import numpy as np
from scipy.sparse import dok_matrix
from bidict import bidict

ctypedef (int,int,float) SAPPair

cdef struct Stack:
    int element
    Stack* btm

cdef Stack* push(Stack* stack, int element):
    cdef Stack *snew = <Stack *> malloc(sizeof(Stack))
    snew[0].element = element
    snew[0].btm = stack
    return snew

cdef (Stack*, int) pop(Stack* stack):
    cdef Stack tmp = stack[0]
    free(stack)
    return tmp.btm, tmp.element

cdef void freestack(Stack* stack):
    cdef Stack *current = stack
    cdef Stack *tmp = NULL
    while current != NULL:
        tmp = current[0].btm
        free(current)
        current = tmp

cdef struct Node:
    SAPPair *predecessors
    SAPPair *successors
    int predcount, succcount 

cdef struct TarjanNode:
    int index, lowlink
    int onstack

cdef struct SubMDP:
    int* E
    SAPPair* F
    int nodecount, sapcount

cdef class Graph:
    cdef Node *nodes
    cdef int nodecount

    def __cinit__(self, P=None, index_by_state_action=None):
        if P is not None and index_by_state_action is not None:
            self.nodecount = P.shape[1]
            self.nodes = <Node *> malloc(self.nodecount * sizeof(Node))
            for i in range(self.nodecount):
                self.nodes[i] = Node(NULL,NULL,0,0)
            for (i,d),p in P.items():
                s,a = index_by_state_action.inv[i]
                self.add_successor(s,a,p,d)

    def get_nodecount(self):
        return self.nodecount

    def subgraph(self, vmask):
        # compute the size of the subgraph (=#vertices)
        subgraphsize = 0
        sub_to_sup = bidict()
        for i in range(self.nodecount):
            if vmask[i] == 1: 
                sub_to_sup[subgraphsize] = i
                subgraphsize += 1

        cdef Node *nodes = <Node *> malloc(subgraphsize*sizeof(Node)) 
        for i in range(subgraphsize):
            nodes[i] = Node(NULL,NULL,0,0)
        sgraph = Graph()
        sgraph.nodes = nodes
        sgraph.nodecount = subgraphsize

        cdef SAPPair* successors
        for i in range(subgraphsize):
            orig = sub_to_sup[i]
            removed_actions = set() # ignore all actions which have successors that are not masked
            for d,a,p in self.successors(orig):
                if vmask[d] == 0:
                    removed_actions.add(a)
            for d,a,p in self.successors(orig):
                if a not in removed_actions:
                    sgraph.add_successor(i,a,p,sub_to_sup.inv[d])

        return sgraph, sub_to_sup

    cdef void add_successor(self, int fromidx, int action, float prob, int toidx):
        cdef Node* fromnode = &self.nodes[fromidx]
        cdef Node* tonode = &self.nodes[toidx]

        fromnode[0].succcount += 1
        cdef SAPPair *newsuccs = <SAPPair *> malloc(fromnode[0].succcount * sizeof(SAPPair))
        for i in range(fromnode[0].succcount-1):
            newsuccs[i] = fromnode[0].successors[i]
        newsuccs[fromnode[0].succcount-1] = (toidx, action, prob)
        free(fromnode[0].successors)
        fromnode[0].successors = newsuccs

        tonode[0].predcount += 1
        cdef SAPPair *newpreds = <SAPPair *> malloc(tonode[0].predcount * sizeof(SAPPair))
        for i in range(tonode[0].predcount-1):
            newpreds[i] = tonode[0].predecessors[i]
        newpreds[tonode[0].predcount-1] = (fromidx, action, prob)
        free(tonode[0].predecessors)
        tonode[0].predecessors = newpreds

    def successors(self, nodeidx, actionidx=None):
        cdef Node *node = &self.nodes[nodeidx]
        for i in range(node[0].succcount):
            if actionidx is None or actionidx == node[0].successors[i][1]:
                yield node[0].successors[i]
    
    def predecessors(self, nodeidx, actionidx=None):
        cdef Node *node = &self.nodes[nodeidx]
        for i in range(node[0].predcount):
            if actionidx is None or actionidx == node[0].predecessors[i][1]:
                yield node[0].predecessors[i]

    def __str__(self):
        cdef Node *currentnode
        ret = ""
        for i in range(self.nodecount):
            currentnode = &self.nodes[i]
            ret += str(i) + " ->"
            for j in range(currentnode[0].succcount):
                ret += " " + str(currentnode[0].successors[j])
            ret += "\n"
        return ret

    cdef (int,int,Stack*) strongconnect(self, int v, Stack* stack, TarjanNode* tnodes, 
        int i, int* scs, int sccount):
        
        tnodes[v] = TarjanNode(i, i, 1)
        i += 1
        stack = push(stack, v)

        cdef Node *node = &self.nodes[v]
        for succidx in range(node[0].succcount):
            w = node[0].successors[succidx][0] # -> index of successor state
            if tnodes[w].index == -1:
                i,sccount,stack = self.strongconnect(w,stack,tnodes,i,scs,sccount)
                tnodes[v].lowlink = min(tnodes[v].lowlink,tnodes[w].lowlink)
            elif tnodes[w].onstack:
                tnodes[v].lowlink = min(tnodes[v].lowlink,tnodes[w].index)

        if tnodes[v].lowlink == tnodes[v].index:
            w = -1
            while w != v:
                stack, w = pop(stack)
                tnodes[w].onstack = 0
                scs[w] = sccount
            sccount += 1

        return i,sccount,stack


    def strongly_connected_components(self):
        # Implementation of Tarjan's Algorithm
        # initialize vector containing strongly connected endcomponents
        cdef int* scs = <int *> malloc(self.nodecount * sizeof(int))
        cdef int sccount = 0

        # initialize a vector containing meta-data for each node
        cdef TarjanNode* tnodes = <TarjanNode *> malloc(self.nodecount * sizeof(TarjanNode))
        for i in range(self.nodecount):
            tnodes[i].index = -1

        cdef Stack *stack = NULL
        for v in range(self.nodecount):
            if tnodes[v].index == -1:
                i,sccount,stack = self.strongconnect(v, stack, tnodes, i, scs, sccount)

        # copy into numpy array
        scs_arr = np.zeros(self.nodecount)
        for i in range(self.nodecount):
            scs_arr[i] = scs[i]
        
        # clear everything up
        free(tnodes)
        free(scs)
        freestack(stack)
        
        return scs_arr, sccount

    def maximal_end_components(self):
        # iteratively create sub-graphs. 
        # but this may be a bit time-consuming, since it involves copying 
        # quite a few nodes from graphs to subgraphs. 
        # possible to share objects and instead just point to parent's objects? 
        # this would avoid unneccessary copying...
        # we should implement the copy-approach first; it's just simpler and we will
        # see whether the algorithm really works.
        ret = np.zeros(self.nodecount)
        mec_counter = 1
        stack = [ (self,[]) ]
        while len(stack) > 0:
            graph,mappings = stack.pop()
            components,compcount = graph.strongly_connected_components()
            
            if compcount == 1:
                # make sure that every node has at least one outgoing edge (one action that can be enabled for states in the MDP)
                ignore_this_graph = False
                for i in range(graph.get_nodecount()):
                    if len(list(graph.successors(i))) == 0:
                        ignore_this_graph = True
                        break
                if ignore_this_graph: continue
                
                # cannot be reduced much further,
                # trace chain of mappings back to root graph 
                states = mappings[-1].keys()
                mapped_states = set()
                for mapping in mappings[::-1]:
                    for state in states:
                        mapped_states.add(mapping[state])
                    states = mapped_states
                    mapped_states = set()
                
                for state in states:
                    ret[state] = mec_counter
                mec_counter += 1
            else:
                sgs = [ graph.subgraph(components == i) for i in range(compcount) ]
                stack += [ (subgraph, mappings + [to_sup]) for subgraph,to_sup in sgs ]
        return ret, mec_counter-1


    def reachable(self, fromset, direction, blocklist=set()):
        assert len(fromset) > 0
        assert direction in ["forward", "backward"]

        cdef int* reachablemask = <int *> malloc(self.nodecount * sizeof(int))
        cdef int* instack = <int *> malloc(self.nodecount * sizeof(int))
        cdef Stack *stack = NULL
        cdef int currentidx
        cdef Node *currentnode
        cdef int neighbourcount
        cdef SAPPair* neighbours
        cdef int* blockmask = <int *> malloc(self.nodecount * sizeof(int))

        # setup reachable mask, blockmask and stack
        for i in range(self.nodecount):
            reachablemask[i] = 0
            instack[i] = 0
            blockmask[i] = 0
        
        for idx in fromset:
            instack[idx] = 1
            stack = push(stack, idx)

        for idx in blocklist:
            blockmask[idx] = 1

        while stack != NULL:
            stack, currentidx = pop(stack)
            currentnode = &self.nodes[currentidx]
            instack[currentidx] = 0
            reachablemask[currentidx] = 1

            if not blockmask[currentidx]:
                if direction == "forward":
                    neighbourcount = currentnode[0].succcount
                    neighbours = currentnode[0].successors
                else:
                    neighbourcount = currentnode[0].predcount
                    neighbours = currentnode[0].predecessors

                for idx in range(neighbourcount):
                    neighidx,_,_ = neighbours[idx]
                    if not reachablemask[neighidx] and not instack[neighidx]:
                        instack[neighidx] = 1
                        stack = push(stack, neighidx)

        ret = np.zeros(self.nodecount, dtype=np.bool)
        for i in range(self.nodecount):
            ret[i] = reachablemask[i]

        free(blockmask)
        free(reachablemask)
        free(instack)
        freestack(stack)
        return ret
    
    cdef void __free_nodes(self):
        for i in range(self.nodecount):
            free(self.nodes[i].predecessors)
            free(self.nodes[i].successors)
        free(self.nodes)

    def __dealloc__(self):
        self.__free_nodes()



