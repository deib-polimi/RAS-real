
from .controller import Controller
import casadi
import numpy as np
import time
from .circular import CircularArray

class OPTCTRLROBUST(Controller):
    
    estimationWindow = 30;
    rtSamples = None
    cSamples = None
    userSamples = None
    
    def __init__(self, period, init_cores, min_cores, max_cores, st=0.8,stime=None):
        super().__init__(period, init_cores, min_cores, max_cores, st)
        if(not isinstance(stime, list)):
            self.stime = [stime]
        self.generator = None
        #self.estimator = QNEstimaator()
        self.rtSamples = [[]]
        self.cSamples = [[]]
        self.userSamples = [[]]
        self.Ik=CircularArray(size=200)
        self.noise=CircularArray(size=200)
    
    # def OPTController(self,e, tgt, C,maxCore):
    #     optCTRL = Model() 
    #     optCTRL.hideOutput()
    #
    #     nApp=len(tgt)
    #
    #     T=[optCTRL.addVar("t%d"%(i), vtype="C", lb=0, ub=None) for i in range(nApp)]
    #     S=[optCTRL.addVar("s%d"%(i), vtype="C", lb=10**-3, ub=maxCore) for i in range(nApp)]
    #     D=[optCTRL.addVar("d%d"%(i), vtype="B") for i in range(nApp)]
    #     E_l1 = [optCTRL.addVar(vtype="C", lb=0, ub=None) for i in range(nApp)]
    #
    #     sSum=0
    #     obj=0;
    #     for i in range(nApp):
    #         sSum+=S[i]
    #         obj+=E_l1[i]/tgt[i]
    #
    #     optCTRL.addCons(sSum<=maxCore)
    #
    #     for i in range(nApp):
    #         optCTRL.addCons(T[i] <= S[i] / e[i])
    #         optCTRL.addCons(T[i] <= C[i] / e[i])
    #         optCTRL.addCons(T[i] >= S[i] / e[i] - C[i] / e[i] * D[i])
    #         optCTRL.addCons(T[i] >= C[i] / e[i] - C[i] / e[i] * (1 - D[i]))
    #         optCTRL.addCons(E_l1[i] >= ((C[i]/T[i])-tgt[i]))
    #         optCTRL.addCons(E_l1[i] >= -((C[i]/T[i])-tgt[i]))
    #
    #
    #     optCTRL.setObjective(obj)
    #
    #     optCTRL.optimize()
    #     sol = optCTRL.getBestSol()
    #     return [sol[S[i]] for i in range(nApp)]
    
    # def OPTController(self, e, tgt, C, maxCore):
    #     #print("stime:=", e, "tgt:=", tgt, "user:=", C)
    #     if(np.sum(C)>0):
    #         self.model = casadi.Opti() 
    #         nApp = len(tgt)
    #
    #         T = self.model.variable(1, nApp);
    #         S = self.model.variable(1, nApp);
    #         E_l1 = self.model.variable(1, nApp);
    #
    #         self.model.subject_to(T >= 0)
    #         self.model.subject_to(self.model.bounded(0, S, maxCore))
    #         self.model.subject_to(E_l1 >= 0)
    #
    #         sSum = 0
    #         obj = 0;
    #         for i in range(nApp):
    #             sSum += S[0, i]
    #             # obj+=E_l1[0,i]
    #             obj += (T[0, i] / C[i] - 1.0 / tgt[i]) ** 2
    #
    #        # self.model.subject_to(sSum <= maxCore)
    #
    #         for i in range(nApp):
    #             # optCTRL.addCons(T[i] <= S[i] / e[i])
    #             # optCTRL.addCons(T[i] <= C[i] / e[i])
    #             # optCTRL.addCons(T[i] >= S[i] / e[i] - C[i] / e[i] * D[i])
    #             # optCTRL.addCons(T[i] >= C[i] / e[i] - C[i] / e[i] * (1 - D[i]))
    #             # optCTRL.addCons(E_l1[i] >= ((C[i]/T[i])-tgt[i]))
    #             # optCTRL.addCons(E_l1[i] >= -((C[i]/T[i])-tgt[i]))
    #             self.model.subject_to(T[0, i] == casadi.fmin(S[0, i] / e[i], C[i] / e[i]))
    #
    #         # self.model.subject_to((E_l1[0,i]+tgt[i])>=((C[i]/T[0,i])))
    #         # self.model.subject_to((E_l1[0,i]-tgt[i])>=-((C[i]/T[0,i])))
    #
    #         self.model.minimize(obj)    
    #         optionsIPOPT = {'print_time':False, 'ipopt':{'print_level':0}}
    #         # self.model.solver('osqp',{'print_time':False,'error_on_fail':False})
    #         self.model.solver('ipopt', optionsIPOPT) 
    #
    #         sol = self.model.solve()
    #         if(nApp==1):
    #             return sol.value(S)
    #         else:
    #             return sol.value(S).tolist()
    #     else:
    #         return 10**(-3)
    #
    #     # optCTRL.optimize()
    #     # sol = optCTRL.getBestSol()
    #     # return [sol[S[i]] for i in range(nApp)]
    
    def OPTController(self, e, tgt, C):
        #print("stime:=", e, "tgt:=", tgt, "user:=", C)
        if(np.sum(C)>0):
            self.model = casadi.Opti("conic") 
            nApp = len(tgt)
            
            T = self.model.variable(1, nApp);
            S = self.model.variable(1, nApp);

            self.model.subject_to(T >= 0)
            self.model.subject_to(self.model.bounded(self.min_cores, S, self.max_cores))
            
            obj=0;
            for i in range(nApp):
                #self.model.subject_to(T[0, i] == casadi.fmin(C[i] / (1.0+e[i]),S[0, i] / e[i]))
                self.model.subject_to(T[0, i]<= C[i] / (1.0+e[i]))
                self.model.subject_to(T[0, i]<= S[0, i] / e[i])
                obj+=(C[i]-(1+tgt[i])*T[0, i])**2+0.000000*S[0, i]
        
            self.model.minimize(obj)    
            # self.model.solver('osqp',{'print_time':False,'error_on_fail':False})
            optionsIPOPT={'print_time':False,'ipopt':{'print_level':0}}
            optionsOSQP={'print_time':False,'osqp':{'verbose':0}}
            self.model.solver('osqp',optionsOSQP) 
        
            sol = self.model.solve()
            #print(C[0]/sol.value(T),sol.value(obj),tgt)
            if(nApp==1):
                return sol.value(S)
            else:
                return sol.value(S).tolist()
        else:
            return 10**(-3)
    
    def estimate(self,rt,s,c):
        self.model = casadi.Opti("conic")
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
        self.model.solver('osqp',{'print_time':False,'osqp':{'verbose':0}}) 
        
        sol=self.model.solve()
        return sol.value(e)
            
        
    
    def addRtSample(self, rt, u, c):
        if(len(self.rtSamples) >= self.estimationWindow):
            # print("rolling",rt, u, c)
            # print(self.cSamples)
            self.rtSamples = np.roll(self.rtSamples, [-1, 0], 0)
            self.cSamples = np.roll(self.cSamples, [-1, 0], 0)
            self.userSamples = np.roll(self.userSamples, [-1, 0], 0)
            
            # print(self.cSamples)
            self.rtSamples[-1] = rt
            self.cSamples[-1] = c
            self.userSamples[-1] = u
            
            # print(self.cSamples[-1],c,np.round(c,5))
        else:
            print("adding", rt, u, c)
            self.rtSamples.append(rt)
            self.cSamples.append(list(map(float,c)))
            self.userSamples.append(u)

    def cmpNoise(self,core=None,users=None,st=None,rtm=None):
        print(f"## core={core},users={users},st={st},rtm={rtm}")
        #modelnoise
        Tpred=min([users/(1.0+st),core/st])
        pred=(users/Tpred)-1.0
        noise=rtm-pred
        print(f"###pred={pred}; noise={noise};")
        return max(noise/pred,0)
        
    def control(self, t):
        rt = self.monitoring.getRT()
        users = None
        if(self.generator != None):
            users = self.generator.f(t + 1)    
        else:
            users = self.monitoring.getUsers()
        
        cores = self.cores
        
        # legacy nel caso si usa il controllore per la singola app
        if(not isinstance(rt, list)):
            rt = [rt]
            users = [users]
            cores = [cores]
        
        #cerco di stimare il throughput, cosi da stimare il numero di utenti e il rispettivo tempo di servizio
        #print("ncmp",len(np.array(self.monitoring.getAllRTs())),"t",t)
        self.addRtSample(np.maximum(rt,[0]), users, cores)
        
        # mRt = np.array(self.rtSamples).mean(axis=0)
        # mCores = np.array(self.cSamples).mean(axis=0)
        # mUsers = np.array(self.userSamples).mean(axis=0)
        
        # i problemi di stima si possono parallelizzare
        for app in range(len(rt)):
            stime = self.estimate(np.array(self.rtSamples), 
                                                      np.array(self.cSamples),
                                                      np.array(self.userSamples)) 
            if(stime is not None):
                self.stime[app]=stime
        
        #if(t>0 and rt[0]-self.setpoint[0]>0):
        #    self.Ik.append(rt[0]-self.setpoint[0])

        
        ny=self.cmpNoise(core=self.cores,users=self.generator.f(t),st=self.stime[0],rtm=rt[0])
        if(ny>0):
            self.noise.append(ny)

        up99=0.0
        if(len(self.userSamples)>3):
            print(np.gradient(np.array(self.userSamples)))
            if(np.gradient(np.array(self.userSamples))[-1]>0):
                self.Ik.append(np.gradient(np.array(self.userSamples))[-1])
                up99=np.percentile(self.Ik.arr,99)
        
        np99=np.percentile(self.noise.arr,99)
        self.stime[0]=self.stime[0]*(1.0+np99)
        print(f"###p95 {np99},{up99}")

        #self.cores=max(self.OPTController(self.stime, self.setpoint, users)+0.0001*self.Ik, self.min_cores)
        users[0]+=up99
        self.cores=max(self.OPTController(self.stime, self.setpoint, users), self.min_cores)
    
    def reset(self):
        super().reset()
        self.rtSamples = []
        self.cSamples = []
        self.userSamples = []
    
    def setSLA(self, sla):
        if(not isinstance(sla, list)):
            sla = [sla]
            
        self.sla = sla
        self.setpoint = [s * self.st for s in self.sla]
    
    def __str__(self):
        return super().__str__() + " OPTCTRL: %.2f, l: %.2f h: %.2f " % (self.step, self.l, self.h)
    
if __name__ == '__main__':
    # S=ctrl.OPTController([0.08], [0.25*0.7], [55])
    # print(S)
    import scipy.io as sio
    import numpy as np
    
    ctrl=OPTCTRL(period=1, init_cores=1, min_cores=0.1, max_cores=300, st=1)
    data=sio.loadmat("test_data.mat")
    #estimator=QNEstimaator();
    #print(data["RtLine"][:,1],data["cores"][:,1],data["users"][:,0])
    st=time.time()
    e=ctrl.estimate(data["RtLine"][0:-1,1],data["cores"][0:-1,1], data["users"][0:-1,0])
    ctime=time.time()-st;
    print(e,ctime)
    
    s=ctrl.OPTController([e], [e], [100])
    print(s)
    
    
    
        
