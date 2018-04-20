#  ___________________________________________________________________________
#
#  Pyomo: Python Optimization Modeling Objects
#  Copyright 2017 National Technology and Engineering Solutions of Sandia, LLC
#  Under the terms of Contract DE-NA0003525 with National Technology and
#  Engineering Solutions of Sandia, LLC, the U.S. Government retains certain
#  rights in this software.
#  This software is distributed under the 3-clause BSD License.
#  ___________________________________________________________________________

from pyomo.core.base.PyomoModel import ConcreteModel
from pyomo.solvers.plugins.solvers.gurobi_direct import GurobiDirect
from pyomo.solvers.plugins.solvers.persistent_solver import PersistentSolver
from pyomo.util.plugin import alias
from pyomo.core.kernel.numvalue import value, is_fixed
from pyomo.repn import LinearCanonicalRepn
import collections


class GurobiPersistent(PersistentSolver, GurobiDirect):
    """
    A class that provides a persistent interface to Gurobi. Direct solver interfaces do not use any file io.
    Rather, they interface directly with the python bindings for the specific solver. Persistent solver interfaces
    are similar except that they "remember" their model. Thus, persistent solver interfaces allow incremental changes
    to the solver model (e.g., the gurobi python model or the cplex python model). Note that users are responsible
    for notifying the persistent solver interfaces when changes are made to the corresponding pyomo model.

    Keyword Arguments
    -----------------
    model: ConcreteModel
        Passing a model to the constructor is equivalent to calling the set_instance mehtod.
    type: str
        String indicating the class type of the solver instance.
    name: str
        String representing either the class type of the solver instance or an assigned name.
    doc: str
        Documentation for the solver
    options: dict
        Dictionary of solver options
    """
    alias('gurobi_persistent', doc='Persistent python interface to Gurobi')

    def __init__(self, **kwds):
        kwds['type'] = 'gurobi_persistent'
        PersistentSolver.__init__(self, **kwds)
        GurobiDirect._init(self)

        self._pyomo_model = kwds.pop('model', None)
        if self._pyomo_model is not None:
            self.set_instance(self._pyomo_model, **kwds)

    def _remove_constraint(self, solver_con):
        try:
            self._solver_model.remove(solver_con)
        except self._gurobipy.GurobiError:
            self._solver_model.update()
            self._solver_model.remove(solver_con)

    def _remove_sos_constraint(self, solver_sos_con):
        try:
            self._solver_model.remove(solver_sos_con)
        except self._gurobipy.GurobiError:
            self._solver_model.update()
            self._solver_model.remove(solver_sos_con)

    def _remove_var(self, solver_var):
        try:
            self._solver_model.remove(solver_var)
        except self._gurobipy.GurobiError:
            self._solver_model.update()
            self._solver_model.remove(solver_var)

    def add_var(self, var):
        """
        Add a variable to the solver's model. This will keep any existing model components intact.

        Parameters
        ----------
        var: Var
            The variable to add to the solver's model.
        """
        PersistentSolver.add_var(self, var)

    def add_constraint(self, con):
        """
        Add a constraint to the solver's model. This will keep any existing model components intact.

        Parameters
        ----------
        con: Constraint
        """
        PersistentSolver.add_constraint(self, con)

    def add_sos_constraint(self, con):
        """
        Add an SOS constraint to the solver's model (if supported). This will keep any existing model components intact.

        Parameters
        ----------
        con: SOSConstraint
        """
        PersistentSolver.add_sos_constraint(self, con)

    def _warm_start(self):
        GurobiDirect._warm_start(self)

    def update_var(self, var):
        """Update a single variable in the solver's model.

        This will update bounds, fix/unfix the variable as needed, and
        update the variable type.

        Parameters
        ----------
        var: Var (scalar Var or single _VarData)

        """
        # see PR #366 for discussion about handling indexed
        # objects and keeping compatibility with the
        # pyomo.kernel objects
        #if var.is_indexed():
        #    for child_var in var.values():
        #        self.update_var(child_var)
        #    return
        if var not in self._pyomo_var_to_solver_var_map:
            raise ValueError('The Var provided to update_var needs to be added first: {0}'.format(var))
        gurobipy_var = self._pyomo_var_to_solver_var_map[var]
        vtype = self._gurobi_vtype_from_var(var)
        if var.is_fixed():
            lb = var.value
            ub = var.value
        else:
            lb = -self._gurobipy.GRB.INFINITY
            ub = self._gurobipy.GRB.INFINITY
            if var.has_lb():
                lb = value(var.lb)
            if var.has_ub():
                ub = value(var.ub)
        gurobipy_var.setAttr('lb', lb)
        gurobipy_var.setAttr('ub', ub)
        gurobipy_var.setAttr('vtype', vtype)

    def write(self, filename):
        """
        Write the model to a file (e.g., and lp file).

        Parameters
        ----------
        filename: str
            Name of the file to which the model should be written.
        """
        self._solver_model.write(filename)

    def set_linar_constraint_attr(self, con, attr, val):
        """
        Set the value of an attribute on a gurobi linear constraint.

        Paramaters
        ----------
        con: pyomo.core.base.constraint._GeneralConstraintData
            The pyomo constraint for which the corresponding gurobi constraint attribute
            should be modified.
        attr: str
            The attribute to be modified. Options are:
                CBasis
                DStart
                Lazy
        val: any
            See gurobi documentation for acceptable values.
        """
        if attr in {'Sense', 'RHS', 'ConstrName'}:
            raise ValueError('Linear constraint attr {0} cannot be set with' +
                             ' the set_linear_constraint_attr method. Please use' +
                             ' the remove_constraint and add_constraint methods.'.format(attr))
        self._pyomo_con_to_solver_con_map[con].setAttr(attr, val)

    def set_var_attr(self, var, attr, val):
        """
        Set the value of an attribute on a gurobi variable.

        Paramaters
        ----------
        con: pyomo.core.base.var._GeneralVarData
            The pyomo var for which the corresponding gurobi var attribute
            should be modified.
        attr: str
            The attribute to be modified. Options are:
                Start
                VarHintVal
                VarHintPri
                BranchPriority
                VBasis
                PStart
        val: any
            See gurobi documentation for acceptable values.
        """
        if attr in {'LB', 'UB', 'VType', 'VarName'}:
            raise ValueError('Var attr {0} cannot be set with' +
                             ' the set_var_attr method. Please use' +
                             ' the update_var method.'.format(attr))
        if attr == 'Obj':
            raise ValueError('Var attr Obj cannot be set with' +
                             ' the set_var_attr method. Please use' +
                             ' the set_objective method.')
        self._pyomo_var_to_solver_var_map[var].setAttr(attr, val)

    def get_model_attr(self, attr):
        """
        Get the value of an attribute on the gurobi model.

        Paramaters
        ----------
        attr: str
            The attribute to get. See Gurobi documentation for descriptions of the attributes.
            Options are:
                NumVars
                NumConstrs
                NumSOS
                NumQConstrs
                NumgGenConstrs
                NumNZs
                DNumNZs
                NumQNZs
                NumQCNZs
                NumIntVars
                NumBinVars
                NumPWLObjVars
                ModelName
                ModelSense
                ObjCon
                ObjVal
                ObjBound
                ObjBoundC
                PoolObjBound
                PoolObjVal
                MIPGap
                Runtime
                Status
                SolCount
                IterCount
                BarIterCount
                NodeCount
                IsMIP
                IsQP
                IsQCP
                IsMultiObj
                IISMinimal
                MaxCoeff
                MinCoeff
                MaxBound
                MinBound
                MaxObjCoeff
                MinObjCoeff
                MaxRHS
                MinRHS
                MaxQCCoeff
                MinQCCoeff
                MaxQCLCoeff
                MinQCLCoeff
                MaxQCRHS
                MinQCRHS
                MaxQObjCoeff
                MinQObjCoeff
                Kappa
                KappaExact
                FarkasProof
                TuneResultCount
                LicenseExpiration
                BoundVio
                BoundSVio
                BoundVioIndex
                BoundSVioIndex
                BoundVioSum
                BoundSVioSum
                ConstrVio
                ConstrSVio
                ConstrVioIndex
                ConstrSVioIndex
                ConstrVioSum
                ConstrSVioSum
                ConstrResidual
                ConstrSResidual
                ConstrResidualIndex
                ConstrSResidualIndex
                ConstrResidualSum
                ConstrSResidualSum
                DualVio
                DualSVio
                DualVioIndex
                DualSVioIndex
                DualVioSum
                DualSVioSum
                DualResidual
                DualSResidual
                DualResidualIndex
                DualSResidualIndex
                DualResidualSum
                DualSResidualSum
                ComplVio
                ComplVioIndex
                ComplVioSum
                IntVio
                IntVioIndex
                IntVioSum
        """
        return self._solver_model.getAttr(attr)

    def get_var_attr(self, var, attr):
        """
        Get the value of an attribute on a gurobi var.

        Paramaters
        ----------
        var: pyomo.core.base.var._GeneralVarData
            The pyomo var for which the corresponding gurobi var attribute
            should be retrieved.
        attr: str
            The attribute to get. Options are:
                LB
                UB
                Obj
                VType
                VarName
                X
                Xn
                RC
                BarX
                Start
                VarHintVal
                VarHintPri
                BranchPriority
                VBasis
                PStart
                IISLB
                IISUB
                PWLObjCvx
                SAObjLow
                SAObjUp
                SALBLow
                SALBUp
                SAUBLow
                SAUBUp
                UnbdRay
        """
        return self._pyomo_var_to_solver_var_map[var].getAttr(attr)

    def get_linear_constraint_attr(self, con, attr):
        """
        Get the value of an attribute on a gurobi linear constraint.

        Paramaters
        ----------
        con: pyomo.core.base.constraint._GeneralConstraintData
            The pyomo constraint for which the corresponding gurobi constraint attribute
            should be retrieved.
        attr: str
            The attribute to get. Options are:
                Sense
                RHS
                ConstrName
                Pi
                Slack
                CBasis
                DStart
                Lazy
                IISConstr
                SARHSLow
                SARHSUp
                FarkasDual
        """
        return self._pyomo_con_to_solver_con_map[con].getAttr(attr)

    def get_sos_attr(self, con, attr):
        """
        Get the value of an attribute on a gurobi sos constraint.

        Paramaters
        ----------
        con: pyomo.core.base.sos._SOSConstraintData
            The pyomo SOS constraint for which the corresponding gurobi SOS constraint attribute
            should be retrieved.
        attr: str
            The attribute to get. Options are:
                IISSOS
        """
        return self._pyomo_con_to_solver_con_map[con].getAttr(attr)

    def get_quadratic_constraint_attr(self, con, attr):
        """
        Get the value of an attribute on a gurobi quadratic constraint.

        Paramaters
        ----------
        con: pyomo.core.base.constraint._GeneralConstraintData
            The pyomo constraint for which the corresponding gurobi constraint attribute
            should be retrieved.
        attr: str
            The attribute to get. Options are:
                QCSense
                QCRHS
                QCName
                QCPi
                QCSlack
                IISQConstr
        """
        return self._pyomo_con_to_solver_con_map[con].getAttr(attr)

    def set_gurobi_param(self, param, val):
        """
        Set a gurobi parameter.

        Parameters
        ----------
        param: str
            The gurobi parameter to set. Options include any gurobi parameter.
            Please see the Gurobi documentation for options.
        val: any
            The value to set the parameter to. See Gurobi documentation for possible values.
        """
        self._solver_model.setParam(param, val)

    def get_gurobi_param_info(self, param):
        """
        Get information about a gurobi parameter.

        Parameters
        ----------
        param: str
            The gurobi parameter to get info for. See Gurobi documenation for possible options.

        Returns
        -------
        six-tuple containing the parameter name, type, value, minimum value, maximum value, and default value.
        """
        return self._solver_model.getParamInfo(param)

    def _intermediate_callback(self, gurobi_model, where):
        self._callback_func(self._pyomo_model, self, where)

    def set_callback(self, func=None):
        """
        Specify a callback for gurobi to use.

        Parameters
        ----------
        func: function
            The function to call. The function should have two arguments. The first will be the pyomo model being
            solved. The second will be the GurobiPersistent instance. The third will be an enum member of
            gurobipy.GRB.Callback. This will indicate where in the branch and bound algorithm gurobi is at. For
            example:

            >>> from gurobipy import GRB
            >>> import pyomo.environ as pe
            >>> m = pe.ConcreteModel()
            >>> m.x = pe.Var(within=pe.Binary)
            >>> m.y = pe.Var(within=pe.Binary)
            >>> m.obj = pe.Objective(expr=m.x + m.y)
            >>> opt = pe.SolverFactory('gurobi_persistent')
            >>> opt.set_instance(m)
            >>> def my_callback(cb_m, cb_opt, cb_where):
            ...     if cb_where == GRB.Callback.MIPNODE:
            ...         status = cb_opt.cbGet(GRB.Callback.MIPNODE_STATUS)
            ...         if status == GRB.OPTIMAL:
            ...             cb_opt.cbGetNodeRel([cb_m.x, cb_m.y])
            ...             if cb_m.x.value + cb_m.y.value > 1.1:
            ...                 cb_opt.cbCut(pe.Constraint(expr=cb_m.x + cb_m.y <= 1))
            >>> opt.set_callback(my_callback)
            >>> opt.solve()
        """
        if func is not None:
            self._callback = self._intermediate_callback
            self._callback_func = func
        else:
            self._callback = None
            self._callback_func = None

    def cbCut(self, con):
        """
        Add a cut within a callback.

        Parameters
        ----------
        con: pyomo.core.base.constraint._GeneralConstraintData
            The cut to add
        """
        if not con.active:
            raise ValueError('cbCut expected an active constraint.')

        if is_fixed(con.body):
            raise ValueError('cbCut expected a non-trival constraint')

        if con._linear_canonical_form:
            gurobi_expr, referenced_vars = self._get_expr_from_pyomo_repn(con.canonical_form(),
                                                                          self._max_constraint_degree)
        elif isinstance(con, LinearCanonicalRepn):
            gurobi_expr, referenced_vars = self._get_expr_from_pyomo_repn(con, self._max_constraint_degree)
        else:
            gurobi_expr, referenced_vars = self._get_expr_from_pyomo_expr(con.body, self._max_constraint_degree)

        if con.has_lb():
            if con.has_ub():
                raise ValueError('Range constraints are not supported in cbCut.')
            if not is_fixed(con.lower):
                raise ValueError('Lower bound of constraint {0} is not constant.'.format(con))
        if con.has_ub():
            if not is_fixed(con.upper):
                raise ValueError('Upper bound of constraint {0} is not constant.'.format(con))

        if con.equality:
            self._solver_model.cbCut(lhs=gurobi_expr, sense=self._gurobipy.GRB.EQUAL,
                                     rhs=value(con.lower))
        elif con.has_lb() and (value(con.lower) > -float('inf')):
            self._solver_model.cbCut(lhs=gurobi_expr, sense=self._gurobipy.GRB.GREATER_EQUAL,
                                     rhs=value(con.lower))
        elif con.has_ub() and (value(con.upper) < float('inf')):
            self._solver_model.cbCut(lhs=gurobi_expr, sense=self._gurobipy.GRB.LESS_EQUAL,
                                     rhs=value(con.upper))
        else:
            raise ValueError('Constraint does not have a lower or an upper bound {0} \n'.format(con))

    def cbGet(self, what):
        return self._solver_model.cbGet(what)

    def cbGetNodeRel(self, vars):
        """
        Load the values of the specified variables from the node relaxation solution at the current node.

        Parameters
        ----------
        vars: Var or iterable of vars
        """
        if not isinstance(vars, collections.Iterable):
            vars = [vars]
        gurobi_vars = [self._pyomo_var_to_solver_var_map[i] for i in vars]
        var_values = self._solver_model.cbGetNodeRel(gurobi_vars)
        for i, v in enumerate(vars):
            v.value = var_values[i]

    def cbGetSolution(self, vars):
        """
        Load the values of the specified variables from the new MIP solution.

        Parameters
        ----------
        vars: iterable of vars
        """
        if not isinstance(vars, collections.Iterable):
            vars = [vars]
        gurobi_vars = [self._pyomo_var_to_solver_var_map[i] for i in vars]
        var_values = self._solver_model.cbGetSolution(gurobi_vars)
        for i, v in enumerate(vars):
            v.value = var_values[i]

    def cbLazy(self, con):
        """
        Add a lazy constraint within a callback. See gurobi docs for details.

        Parameters
        ----------
        con: pyomo.core.base.constraint._GeneralConstraintData
            The lazy constraint to add
        """
        if not con.active:
            raise ValueError('cbLazy expected an active constraint.')

        if is_fixed(con.body):
            raise ValueError('cbLazy expected a non-trival constraint')

        if con._linear_canonical_form:
            gurobi_expr, referenced_vars = self._get_expr_from_pyomo_repn(con.canonical_form(),
                                                                          self._max_constraint_degree)
        elif isinstance(con, LinearCanonicalRepn):
            gurobi_expr, referenced_vars = self._get_expr_from_pyomo_repn(con, self._max_constraint_degree)
        else:
            gurobi_expr, referenced_vars = self._get_expr_from_pyomo_expr(con.body, self._max_constraint_degree)

        if con.has_lb():
            if con.has_ub():
                raise ValueError('Range constraints are not supported in cbLazy.')
            if not is_fixed(con.lower):
                raise ValueError('Lower bound of constraint {0} is not constant.'.format(con))
        if con.has_ub():
            if not is_fixed(con.upper):
                raise ValueError('Upper bound of constraint {0} is not constant.'.format(con))

        if con.equality:
            self._solver_model.cbLazy(lhs=gurobi_expr, sense=self._gurobipy.GRB.EQUAL,
                                      rhs=value(con.lower))
        elif con.has_lb() and (value(con.lower) > -float('inf')):
            self._solver_model.cbLazy(lhs=gurobi_expr, sense=self._gurobipy.GRB.GREATER_EQUAL,
                                      rhs=value(con.lower))
        elif con.has_ub() and (value(con.upper) < float('inf')):
            self._solver_model.cbLazy(lhs=gurobi_expr, sense=self._gurobipy.GRB.LESS_EQUAL,
                                      rhs=value(con.upper))
        else:
            raise ValueError('Constraint does not have a lower or an upper bound {0} \n'.format(con))

    def cbSetSolution(self, vars, solution):
        if not isinstance(vars, collections.Iterable):
            vars = [vars]
        gurobi_vars = [self._pyomo_var_to_solver_var_map[i] for i in vars]
        self._solver_model.cbSetSolution(gurobi_vars, solution)

    def cbUseSolution(self):
        return self._solver_model.cbUseSolution()
