class Monitoring:
    def __init__(self, window, sla, reducer=lambda x: sum(x)/len(x)):
        self.reducer = reducer
        self.window = window
        self.sla = sla
        self.reset()

    def tick(self, t, rt, users, cores):
        for i in range(1, len(self.time)+1):
            if t - self.time[-i] > self.window:
                try:
                    del self.rts[-i]
                    del self.users[-i]
                except:
                    break

        self.time.append(t)
        self.rts.append(rt)
        self.users.append(users)
        self.allRts.append(self.getRT())
        self.allUsers.append(self.getUsers())
        self.allCores.append(cores)

    def getUsers(self):
        if not len(self.users): return 0
        return self.reducer(self.users)

    def getRT(self):
        if not len(self.rts): return 0
        return self.reducer(self.rts)

    def getViolations(self):
        return sum([1 if rt > self.sla else 0 for rt in self.allRts])

    def getAllRTs(self):
        return self.allRts
    def getAllUsers(self):
        return self.allUsers
    def getAllCores(self):
        return self.allCores
    def reset(self):
        self.allRts = []
        self.allUsers = []
        self.allCores = []
        self.rts = []
        self.users = []
        self.time = []