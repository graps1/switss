from ..utils import cast_dok_matrix
from . import SolverResult
from scipy.sparse import dok_matrix
import pulp
import numpy as np

class MILP:
    """
    A MILP can either be initialized through a specification of coefficient matrices and -vectors 
    or manually, i.e. by adding variables, constraints and the objective function by hand.

    .. code-block::

        # example for a MILP instance. optimal result should be x_opt=[2,6].
        # this is the same as the LP instance but with an added integer constraint for the first variable.
        A = np.matrix([[2,1],[4,-1],[-8,2],[-1,0],[0,-1]])
        b = np.array([10,8,2,0,0])
        opt = np.array([1,1])
        domains = ["integer", "real"]
        milp = MILP.from_coefficients(A,b,opt,domains,objective="max")

        result = milp.solve(solver="cbc")
        print(result)

    .. code-block::

        # the same as the last MILP, but constraints and objective function are added manually.
        milp = MILP(objective="max")
        var1, var2 = milp.add_variables("integer", "real")
        milp.add_constraint([(var1, 2), (var2, 1)], "<=", 10)
        milp.add_constraint([(var1, 4), (var2, -1)], "<=", 8)
        milp.add_constraint([(var1, -8), (var2, 2)], "<=", 2)
        milp.add_constraint([(var1, 1)], ">=", 0)
        milp.add_constraint([(var2, 1)], ">=", 0)
        milp.set_objective_function([(var1, 1), (var2, 1)])

        result = milp.solve(solver="cbc")
        print(result)
    """

    
    def __init__(self, objective="min"):
        """Initializes an empty MILP.
        
        :param objective: Whether the problem should minimize or maximize ("min" or "max"), defaults to "min"
        :type objective: str, optional
        """        
        assert objective in ["min", "max"]
        objective = { "min" : pulp.LpMinimize, "max" : pulp.LpMaximize }[objective]
        self.__pulpmodel = pulp.LpProblem("",objective)
        self.__variables = [] 
        self.__constraint_iter = 0
        self.__set_objective_function = False

    def solve(self, solver="cbc"):
        """Solves this problem and returns the problem result.
        
        :param solver: The solver that should be used. Currently supported are "cbc", "gurobi", "glpk" and "cplex", defaults to "cbc"
        :type solver: str, optional
        :return: Result.
        :rtype: solver.SolverResult
        """        
        assert solver in ["gurobi","cbc","glpk","cplex"]

        if solver == "gurobi":
            self.__pulpmodel.setSolver(pulp.GUROBI_CMD(
                options=[("epgap",0), ("MIPGapAbs",0), ("FeasibilityTol",1e-9), ("IntFeasTol",1e-9)]))
        elif solver == "cbc":
            self.__pulpmodel.setSolver(pulp.PULP_CBC_CMD(fracGap=1e-9))
        elif solver == "glpk":
            self.__pulpmodel.setSolver(pulp.GLPK_CMD())
        elif solver == "cplex":
            self.__pulpmodel.setSolver(pulp.CPLEX_PY())

        self.__pulpmodel.solve()

        status = {   1:"optimal", 
                    -1:"infeasible", 
                    -2:"unbounded", 
                    -3:"undefined"}[self.__pulpmodel.status]
        result_vector = np.array([var.value() for var in self.__variables])
        value = self.__pulpmodel.objective.value()

        return SolverResult(status, result_vector, value)

    def _assert_expression(self, expression):
        for idx,(var,coeff) in enumerate(expression):
            assert var >= 0 and var < len(self.__variables), "Variable %s does not exist (@index=%d)." % (var, idx)
            assert isinstance(coeff, (float,int)), "Coefficient coeff=%s is not a number (@index=%d)." % (coeff, idx)

    def _expr_to_pulp(self, expression):
        for var, coeff in expression:
            yield self.__variables[var], coeff

    def set_objective_function(self, expression):
        """Sets the objective function of the form

        .. math::
            
            \sum_j \sigma_j x_j

        where :math:`\sigma_j` indicates a coefficient and :math:`x_j` a variable.
        
        :param expression: Sum is given as a list of variable/coefficient pairs. Each pair has the coefficient on the
            right and the variable on the left.
        :type expression: List[Tuple[int,float]]
        """        
        self._assert_expression(expression)
        if not self.__set_objective_function:
            self.__set_objective_function = True
            self.__pulpmodel += pulp.LpAffineExpression(self._expr_to_pulp(expression))
        else:
            for var,coeff in expression:
                self.__pulpmodel.objective[self.__variables[var]] = coeff
        
    def add_constraint(self, lhs, sense, rhs):
        """Adds a constraint of the form

        .. math::

            \sum_{j} a_j x_j \circ b
        
        where :math:`\circ \in \{ \leq, =, \geq \}`, :math:`a_j` indicates a coefficient and :math:`x_j` a variable.
        
        :param lhs: Left side of the equation, given as a list of variable/coefficient pairs. Each pair has the coefficient on the
            right and the variable on the left.
        :type lhs: List[Tuple[int,float]]
        :param sense: Type of equation, i.e. "<=", ">=" or "=".
        :type sense: str
        :param rhs: Right side of the equation, i.e. a number.
        :type rhs: float
        """        
        assert sense in ["<=", "=", ">="]
        assert isinstance(rhs, (float,int)), "Right hand side is not a number: rhs=%s" % rhs 
        self._assert_expression(lhs)

        lhs = pulp.LpAffineExpression(self._expr_to_pulp(lhs))
        sense = { "<=" : pulp.LpConstraintLE, 
                  "=" : pulp.LpConstraintEQ, 
                  ">=" : pulp.LpConstraintGE }[sense]

        constraint = pulp.LpConstraint(name="c%d" % self.__constraint_iter, e=lhs, sense=sense, rhs=rhs)
        self.__pulpmodel += constraint
        self.__constraint_iter += 1

    def add_variables(self, *domains):
        """Adds a list of variables to this MILP. Each element in `domains` must be either `integer`, `binary` or `real`.
        
        :return: Index or indices of new variables.
        :rtype: either List[int] or int.
        """        
        l = []
        for domain in domains:
            assert domain in ["integer", "real", "binary"]

            cat = { "real" : pulp.LpContinuous, "integer" : pulp.LpInteger, "binary" : pulp.LpBinary }[domain]
            varidx = len(self.__variables)
            var = pulp.LpVariable("x%d" % varidx, cat=cat)
            self.__variables.append(var)

            if len(domains) == 1:
                return varidx
            else:
                l.append(varidx)
        return l

    @classmethod
    def from_coefficients(cls, A, b, opt, domains, sense="<=", objective="min"):
        """Returns a Mixed Integer Linear Programming (MILP) formulation of a problem
        
        .. math::

            \min_x/\max_x\ \sigma^T x \quad \\text{ s.t. } \quad Ax \circ b, \ x_i \in \mathbb{D}_i,\ \\forall i=1,\dots,N

        where :math:`\circ \in \{ \leq, \geq \}`, :math:`N` is the number of variables and :math:`M`
        the number of linear constraints. :math:`\mathbb{D}_i` indicates
        the domain of each variable. If `A`, `b` and `opt` are not given as a `scipy.sparse.dok_matrix`, 
        they are transformed into that form automatically.
        
        :param A: Matrix for inequality conditions  (:math:`A`).
        :type A: :math:`M \\times N`-Matrix
        :param b: Vector for inequality conditions  (:math:`b`).
        :type b: :math:`M \\times 1`-Matrix
        :param opt: Weights for individual variables in x (:math:`\sigma`). If None, no objective function will be set.
        :type opt: :math:`N \\times 1`-Matrix
        :param domains: Array of strings, e.g. ["real", "integer", "integer", "binary", ...] which indicates the domain for each variable.
        :type domains: List[str]
        :param sense: "<=" or ">=", defaults to "<="
        :type sense: str, optional
        :param objective: "min" or "max", defaults to "min"
        :type objective: str, optional
        :return: The resulting MILP.
        :rtype: solver.MILP
        """

        A = cast_dok_matrix(A).tocsr()
        b = cast_dok_matrix(b)

        opt = cast_dok_matrix(opt)

        model = MILP(objective=objective)

        # initialize problem
        # this adds the variables and the objective function (which is opt^T*x, i.e. sum_{i=1}^N opt[i]*x[i])
        model.add_variables(*[domains[idx] for idx in range(A.shape[1])])
        model.set_objective_function([(idx, opt[idx,0]) for idx in range(A.shape[1])])
        
        # this takes quite a lot of time since accessing the rows is inefficient, even for csr-formats.
        # maybe find a way to compute Ax <= b faster.
        # now: add linear constraints: Ax <= b.
        for constridx in range(A.shape[0]):
            # calculates A[constridx,:]^T * x
            lhs, row = [], A.getrow(constridx)
            for j in row.nonzero()[1]:
                lhs.append((j, A[constridx,j]))
            # adds constraint: A[constridx,:]^T * x <= b[constridx]
            model.add_constraint(lhs, sense, b[constridx,0])

        return model

    def __repr__(self):
        return str(self.__pulpmodel)


class LP(MILP):
    """
    An LP can either be initialized through a specification of coefficient matrices and -vectors 
    or manually, i.e. by adding variables, constraints and the objective function by hand.

    .. code-block::

        # example for a LP instance. optimal result should be x_opt=[1.5,7.0].
        A = np.matrix([[2,1],[4,-1],[-8,2],[-1,0],[0,-1]])
        b = np.array([10,8,2,0,0])
        opt = np.array([1,1])
        lp = LP.from_coefficients(A,b,opt,objective="max")

        result = lp.solve(solver="cbc")
        print(result)
    
    .. code-block::

        # the same as the last LP, but constraints and objective function are added manually.
        lp = LP(objective="max")
        var1, var2 = lp.add_variables(2)
        lp.add_constraint([(var1, 2), (var2, 1)], "<=", 10)
        lp.add_constraint([(var1, 4), (var2, -1)], "<=", 8)
        lp.add_constraint([(var1, -8), (var2, 2)], "<=", 2)
        lp.add_constraint([(var1, 1)], ">=", 0)
        lp.add_constraint([(var2, 1)], ">=", 0)
        lp.set_objective_function([(var1, 1), (var2, 1)])

        result = lp.solve(solver="cbc")
        print(result)
    """

    @classmethod
    def from_coefficients(cls, A, b, opt, sense="<=",objective="min"):
        """Returns a Linear Programming (LP) formulation of a problem

        .. math::

            \min_x/\max_x\ \sigma^T x \quad \\text{s.t.}\quad Ax \circ b

        where :math:`\circ \in \{\leq,\geq\}` :math:`N` is the number of
        variables and :math:`M` the number of linear constraints.
        If `A`, `b` and `opt` are not given as a `scipy.sparse.dok_matrix`,
        they are transformed into that form automatically.

        :param A: Matrix for inequality conditions  (:math:`A`).
        :type A: :math:`M \\times N`-Matrix
        :param b: Vector for inequality conditions  (:math:`b`).
        :type b: :math:`M \\times 1`-Matrix
        :param opt: Weights for individual variables in x (:math:`\sigma`).
        :type opt: :math:`N \\times 1`-Matrix
        :param sense: "<=" or ">=", defaults to "<="
        :type sense: str, optional
        :param objective: "min" or "max", defaults to "min"
        :type objective: str, optional
        :return: The resulting LP.
        :rtype: solver.LP
        """
        return MILP.from_coefficients(A,b,opt,["real"]*A.shape[1],sense=sense,objective=objective)

    def add_variables(self, count):
        """Adds a number of variables to the LP.
        
        :param count: The amount of new variables.
        :type count: int
        :return: Index or indices of new variables.
        :rtype: either List[int] or int.
        """        
        return MILP.add_variables(self, *["real"]*count)
