from . import ProblemFormulation, ProblemResult
from farkas.solver import LP, Wrapper
from farkas.model.reachability_form import induced_subsystem

import numpy as np

class QSHeur(ProblemFormulation):
    """The class QSHeur implements a class of iterative heuristics for computing small witnessing subsystems.
    Its goal is to find points in the corresponding Farkas-polytope with a small number of positive entries.
    It works as follows.
    Given a reachability form, let :math:`\\mathcal{F}(\\lambda)` be its Farkas (min- or max-)polytope for a given threshold :math:`\\lambda`.
    Then, the vector :math:`QS(i)` is an optimal solution of the LP:

    .. math::

       \min \mathbf{o}_i \cdot \mathbf{x} \quad \\text{ subj. to } \quad \mathbf{x} \in \\mathcal{F}(\\lambda)

    where :math:`\mathbf{o}_0` is a vector of initial weights (:math:`(1,\ldots,1)` is the default) and :math:`\mathbf{o}_i = \operatorname{upd}(QS(i-1))` for a given update function :math:`\operatorname{upd}` (where pointwise :math:`1/x` if :math:`x \\neq 0`, and a big constant otherwise, is the default). """
    def __init__(self,
                 threshold,
                 min_or_max,
                 iterations = 3,
                 upd_fct = lambda x: 1e7 if x == 0 else 1 / x,
                 solver_name="cbc"):
        super().__init__()
        assert min_or_max in ["min","max"]
        assert solver_name in ["gurobi","cbc"]
        assert (threshold >= 0) and (threshold <= 1)

        self.min_or_max = min_or_max
        self.threshold = threshold
        self.iterations = iterations
        self.solver = Wrapper(solver_name)
        self.upd_fct = upd_fct

    def solve(self, reach_form):
        """Runs the QSheuristic on the Farkas (min- or max-) polytope depending on the value in min_or_max."""
        if self.min_or_max == "min":
            return self.solve_min(reach_form)
        else:
            return self.solve_max(reach_form)

    def solve_min(self, reach_form, initial_weights = None):
        """Runs the QSheuristic on the Farkas min-polytope of a given reachability form for a given threshold."""
        problem_results = dict()
        _,N = reach_form.P.shape

        # sets the initial objective function (all ones is the default value)
        if initial_weights == None:
            current_weights = np.ones(N)
        else:
            assert initial_weights.size == N
            current_weights = initial_weights

        # computes the constraints for the Farkas min-polytope of the given reachability form
        fark_matr,fark_rhs = reach_form.fark_min_constraints(self.threshold)

        # iteratively solves the corresponding LP, and computes the next objective function
        # from the result of the previous round according to the given update function
        for i in range(0,self.iterations):

            heur_i_lp = LP(fark_matr,fark_rhs,current_weights,lowBound=0,upBound=1)
            heur_i_result = self.solver.solve(heur_i_lp)

            if heur_i_result.status == "optimal":
                res_vector = heur_i_result.result
                to_one_if_positive = np.vectorize(lambda x: 1 if x > 0 else 0)
                induced_states = to_one_if_positive(res_vector[:N])
                # computes the subsystem induced by the result of this iteration
                subsys,mapping = induced_subsystem(reach_form,induced_states)
                problem_results[i] = ProblemResult("success",subsys,mapping)

                for x in range(0,N):
                    current_weights[x] = self.upd_fct(heur_i_result.result[x])

            else:
                # failed to optimize LP
                problem_results[i] = ProblemResult(heur_i_result.status)

        return problem_results

    def solve_max(self, reach_form, initial_weights = None):
        """Runs the QSheuristic on the Farkas max-polytope of a given reachability form for a given threshold."""
        problem_results = dict()
        C,N = reach_form.P.shape

        # sets the initial objective function (all ones is the default value)
        if initial_weights == None:
            current_weights = np.ones(C)
        else:
            assert initial_weights.size == C
            current_weights = initial_weights

        # computes the constraints for the Farkas max-polytope of the given reachability form
        fark_matr,fark_rhs = reach_form.fark_max_constraints(self.threshold)

        # iteratively solves the corresponding LP, and computes the next objective function
        # from the result of the previous round according to the given update function
        for i in range(0,self.iterations):
            heur_i_lp = LP(fark_matr,fark_rhs,current_weights,lowBound=0)
            heur_i_result = self.solver.solve(heur_i_lp)

            if heur_i_result.status == "optimal":
                res_vector = heur_i_result.result
                # the states induced by the results vector are those that have a positive entry
                # for some of their actions
                induced_states = np.zeros(N)
                for index in range(0,C):
                    if res_vector[index] > 0:
                        (st,act) = reach_form.index_by_state_action.inv[index]
                        induced_states[st] = 1

                subsys,mapping = induced_subsystem(reach_form,induced_states)
                problem_results[i] = ProblemResult("success",subsys,mapping)

                for x in range(0,C):
                    current_weights[x] = self.upd_fct(heur_i_result.result[x])

            else:
                # failed to optimize LP
                problem_results[i] = ProblemResult(heur_i_result.status)

        return problem_results
