import math

from .controller import Controller

MAX_SCALE_OUT_TIMES = 100

class CTControllerScaleX(Controller):
    def __init__(self, period, init_cores, min_cores, max_cores, BC=0.5, DC=0.95, st=0.8,
                 anti_windup=False, e_clip=None, error_form="inverse",
                 rt_deadband_frac=0.0):
        """PI controller for autoscaling.

        Convention: `e > 0` means RT too high (need more cores), `e < 0` means
        RT too low (can scale down). All three error forms preserve this
        convention (positive → scale up).

        Args:
            error_form: "inverse" (legacy: e = 1/sp − 1/rt; asymmetric gain),
                        "linear"  (e = (rt − sp)/sp; symmetric, dimensionless),
                        "log"     (e = log(rt) − log(sp); constant relative
                                   sensitivity, Hellerstein 2004 standard).
            anti_windup: if True, applies Astrom-Hagglund back-calculation
                         (currently uses K_aw = 1/DC — this formula is REVISITED
                         in Step 2 of the PI tuning chain).
            e_clip:      optional symmetric clip on error magnitude.
        """
        super().__init__(period, init_cores, min_cores, max_cores, st=st)
        self.BC = BC
        self.DC = DC
        self.old_cores = self.init_cores
        self.xc_prec = 0
        self.anti_windup = anti_windup
        self.e_clip = e_clip
        self.error_form = error_form
        self.rt_deadband_frac = rt_deadband_frac

    def reset(self):
        super().reset()
        self.xc_prec = 0.0

    def control(self, t):
        rt = self.monitoring.getRT()
        if rt == 0:
            return self.init_cores

        # Step 4 (CT-deadband): hold cores when RT is within tolerance of setpoint.
        # Mitigates limit-cycle when optimal continuous c is between two integers.
        if self.rt_deadband_frac > 0.0 and \
           abs(rt - self.setpoint) < self.rt_deadband_frac * self.setpoint:
            return  # cores unchanged this tick

        if self.error_form == "linear":
            # Symmetric, dimensionless. de/drt = 1/sp (constant — no asymmetry).
            e = (rt - self.setpoint) / max(self.setpoint, 1e-9)
        elif self.error_form == "log":
            # Constant relative sensitivity; Hellerstein 2004 §8 standard for
            # RT control of queueing systems (RT distributions are ~lognormal).
            e = math.log(max(rt, 1e-9)) - math.log(max(self.setpoint, 1e-9))
        else:
            # Legacy: inverse formulation — asymmetric gain (de/drt = 1/rt²).
            e = 1/self.setpoint - 1/rt
        if self.e_clip is not None:
            e = max(-self.e_clip, min(self.e_clip, e))
        intg = float(self.xc_prec + self.BC * e)
        prop = float(self.DC * e)
        cores_unsat = intg + prop
        max_cores = min(self.max_cores, self.old_cores*MAX_SCALE_OUT_TIMES)
        self.cores = float(min(max(cores_unsat, self.min_cores), max_cores))
        if t < 20 and self.cores < self.init_cores:
            self.cores = float(self.init_cores)
        if self.anti_windup:
            # Step 2 (CT-R2 fix): Astrom-Hagglund back-calculation done correctly.
            # K_aw = 1/T_t with T_t = T_i = K_p/K_i = DC/BC for PI.
            # → K_aw = BC/DC. Single application (no clamping + K_aw double-app).
            K_aw = self.BC / max(self.DC, 1e-3)
            self.xc_prec = self.xc_prec + self.BC * e + K_aw * (self.cores - cores_unsat)
        else:
            self.xc_prec = float(self.cores - prop)
        self.old_cores = self.cores

    def __str__(self):
        return super().__str__() + " BC: %.2f DC: %.2f " % (self.BC, self.DC)
