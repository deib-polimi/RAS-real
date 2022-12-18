from .generator import Generator
from scipy.io import loadmat


class tweetterGen(Generator):
    
    step=None
    tweets=None
    
    def __init__(self, shift=0, bias = 10):
        data=loadmat("./generators/twitter_20210101_730-24_freq120sec.mat")
        self.step=data["step"]
        self.tweets=data["tweets"][0]
        self.maxIndex = len(self.tweets)
        mx = max(self.tweets)
        mn = min(self.tweets)
        self.tweets = [(v - mn)/(mx-mn)*bias+shift for v in self.tweets]

    def f(self, x):
        return self.tweets[int(x) % self.maxIndex]

    def __str__(self):
        return super().__str__()
