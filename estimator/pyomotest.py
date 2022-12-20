from pyomo.environ import *
import time
import scipy.io as sio
import numpy as np
from scipy.linalg._flapack import stzrzf

# V = 40     # liters
# kA = 0.5   # 1/min
# kB = 0.1   # l/min
# CAf = 2.0  # moles/liter
#
# # create a model instance
# model = ConcreteModel()
#
# # create x and y variables in the model
# model.q = Var()
#
# # add a model objective
# model.objective = Objective(expr = model.q*V*kA*CAf/(model.q + V*kB)/(model.q + V*kA), sense=maximize)
#
# # compute a solution using ipopt for nonlinear optimization
#
# st=time.time()
# results = SolverFactory('ipopt').solve(model)
# print(time.time()-st)
# model.pprint()
#
#
# # print solutions
# qmax = model.q()
# CBmax = model.objective()
# print('\nFlowrate at maximum CB = ', qmax, 'liters per minute.')
# print('\nMaximum CB =', CBmax, 'moles per liter.')
# print('\nProductivity = ', qmax*CBmax, 'moles per minute.')

def fmin(a,b):
    return -(-a-b+abs(a-b))/2

def boundX(model,i):
    if(i%2==0):
        return (2,10)
    else:
        return (3,10)
    
def ruleMin(model,i):
    if(i==1):
        return model.y[i]==fmin(model.x[1],model.x[2])
    elif(i==2):
        return model.y[i]==fmin(model.x[3],model.x[4])
    

C=300;
e=0.093
tgt=0.25

model = ConcreteModel()

model.T= Var(bounds=[0,None])
model.S = Var(bounds=[0,None])
#model.E_l1 = Var(bounds=[0,None]);

model.c1=Constraint(expr=model.T<=C/(1.0+e))
model.c2=Constraint(expr=model.T<=model.S/e)
model.objective = Objective(expr=(C-(1+tgt)*model.T)**2+0.000001*model.S,sense=minimize)
st=time.time()
SolverFactory('gplk').solve(model)
print(model.S(),model.T(),C/model.T(),time.time()-st)


# model = ConcreteModel()
#
# #Ti=min(C/(1+e),s/e)
# model.idx=RangeSet(1,4)
# model.idy=RangeSet(1,2)
#
# model.x=Var(model.idx,bounds=boundX)
# model.y=Var(model.idy)

# model.e = 
# model.e1 = Var(bounds=(5,None),initialize=5)
# model.y = Var(bounds=(0,None),initialize=0.0001)
#
# model.c= Constraint(model.idy,rule=ruleMin)

#self.model.set_initial(e,0.0001)

# model.t=[]
# model.er_l1=[]
# for i in range(len(RTm)):
#     model.t+=[Var(bounds=(0,None),initialize=0.0001)]
#     model.er_l1+=[Var(bounds=(0,None),initialize=0.0001)]
#
#
# obj=0;
# for i in range(RTm.shape[0]):
#     #self.model.subject_to(t[i,0]==casadi.fmin(c[i]/(1+e),s[i]/e))
#     #Constraint(expr=t[i]==-U[i]/(1+e)-S[i]/e+sqrt((U[i]/(1+e)-S[i]/e)**2+0.001))
#     #Constraint(expr=model.t[i]==-(-U[i]/(1+model.e)-S[i]/model.e+abs(U[i]/(1+model.e)-S[i]/model.e))/2)
#     #Constraint(expr=model.er_l1[i]>=(U[i]/model.t[i]-(RTm[i]+1)))
#     #Constraint(expr=model.er_l1[i]>=-(U[i]/model.t[i]-(RTm[i]+1)))
#     obj+=model.er_l1[i];

# model.objective = Objective(expr=model.y[1]+model.y[2], sense=minimize)
# results = SolverFactory('ipopt').solve(model)
# print(model.y[1](),model.y[2]())


# self.model.minimize(obj)    
# optionsIPOPT={'print_time':False,'ipopt':{'print_level':0}}
# self.model.solver('ipopt',optionsIPOPT) 
#
# sol=self.model.solve()
# return sol.value(e)