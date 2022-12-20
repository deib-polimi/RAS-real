'''
Created on 31 mar 2021

@author: emilio
'''
import casadi
import time
class QNEstimaator():
    
    model=None
    
    # def estimate(self,rt,s,c):
    #     self.model = casadi.Opti()
    #
    #     # print("rt",rt)
    #     # print("server",s)
    #     # print("client",c)
    #
    #
    #     e = self.model.variable(1,1);
    #     er_l1 = self.model.variable(1,rt.shape[0]);
    #
    #     self.model.subject_to(e>=0)
    #     self.model.subject_to(er_l1>=0)
    #
    #     for i in range(rt.shape[0]):
    #         if(c[i]<s[i]):
    #             self.model.subject_to(er_l1[0,i] >= rt[i]-e)
    #             self.model.subject_to(er_l1[0,i] >= -rt[i]+e)
    #         else:
    #             self.model.subject_to(er_l1[0,i] >= rt[i]-(c[i]/s[i])*e)
    #             self.model.subject_to(er_l1[0,i] >= -rt[i]+(c[i]/s[i])*e)
    #
    #     self.model.minimize(casadi.sum2(er_l1))    
    #     optionsIPOPT={'print_time':False,'ipopt':{'print_level':0}}
    #     self.model.solver('ipopt',optionsIPOPT) 
    #
    #     sol=self.model.solve()
    #     return sol.value(e)
    
    def estimate(self,rt,s,c):
        self.model = casadi.Opti()
        #Ti=min(C/(1+e),s/e)
        e = self.model.variable(1,1);
        self.model.set_initial(e,0.000001)
        t = self.model.variable(rt.shape[0],1);
        self.model.subject_to(e>=0)
        self.model.subject_to(t>=0)
        
        obj=0;
        for i in range(rt.shape[0]):
            self.model.subject_to(t[i,0]==casadi.fmin(c[i]/(1+e),s[i]/e))
            obj+=(c[i]-(rt[i]+1)*t[i,0])**2;
        
        self.model.minimize(obj)    
        optionsIPOPT={'print_time':False,'ipopt':{'print_level':0}}
        self.model.solver('ipopt',optionsIPOPT) 
        
        sol=self.model.solve()
        return sol.value(e)
    

if __name__ == '__main__':
    import scipy.io as sio
    import numpy as np
    data=sio.loadmat("test_data.mat")
    estimator=QNEstimaator();
    #print(data["RtLine"][:,1],data["cores"][:,1],data["users"][:,0])
    st=time.time()
    npoint=-1
    e=estimator.estimate(data["RtLine"][0:npoint,1],data["cores"][0:npoint,1], data["users"][:npoint,0])
    ctime=time.time()-st;
    print(e,ctime)
    
