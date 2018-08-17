# This example should run the same calculation as Example2TRF.py without calling the 
# black box function and should calculate the same result.
     
from pyomo.environ import *

m = ConcreteModel()
m.z = Var(range(3), domain=Reals, initialize=2.)
m.x = Var(range(2), initialize=2.)
m.x[1] = 1.0

m.fix_val1 = Var(domain=PositiveReals,
                  initialize=.0112)
m.fix_val1.fix()

m.fix_val2 = Var(domain=PositiveReals,
                  initialize=.0033)
m.fix_val2.fix()

m.obj = Objective(
   expr=(m.z[0]-1.0)**2 + (m.z[0]-m.z[1])**2 + (m.z[2]-1.0)**2 \
       + (m.x[0]-1.0)**4 + (m.x[1]-1.0)**6 # + m.bb(m.x[0],m.x[1])
)
m.c1 = Constraint(expr=m.x[0] * m.z[0]**2 + 2*(sin(m.x[0] - m.x[1]) + m.fix_val1) - (sin(m.x[0] - m.x[1]) + m.fix_val2) == 2*sqrt(2.0))
m.c2 = Constraint(expr=m.z[2]**4 * m.z[1]**2 + m.z[1] + m.fix_val2 == 8+sqrt(2.0))
