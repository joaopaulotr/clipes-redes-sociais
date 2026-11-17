"""Online peak detector for live chat (spec 002, RF-005).

Pure and clock-free: the caller pushes one weighted message count per second and gets back
the peak strength (z-score) when a peak fires, or None. "Normal" is the past window of the same
live only, so a big channel and a small one calibrate themselves.
"""

from collections import deque
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Detector:
    limiar_z: float = 3.0          # how many standard deviations above normal
    min_msgs_s: float = 2.0        # absolute floor, avoids "peaks" in an empty chat
    janela_normal_s: int = 300     # history used as "normal"
    suavizar_s: int = 5            # short window compared against normal
    aquecimento_s: int = 120       # no peaks before this much history exists
    refratario_s: int = 60         # two peaks closer than this are one (H2, scenario 2)

    _hist: deque = field(default_factory=deque, init=False, repr=False)
    _t: int = field(default=0, init=False)
    _ultimo_pico: int = field(default=-10**9, init=False)

    def empurrar(self, contagem: float) -> float | None:
        """Adds one second. Returns the z-score when a peak fires, else None."""
        self._t += 1
        self._hist.append(float(contagem))
        limite = self.janela_normal_s + self.suavizar_s
        while len(self._hist) > limite:
            self._hist.popleft()
        if len(self._hist) < self.aquecimento_s + self.suavizar_s:
            return None

        dados = np.fromiter(self._hist, dtype=float)
        recente = dados[-self.suavizar_s:]
        passado = dados[:-self.suavizar_s]
        media_recente = float(recente.mean())
        normal = float(passado.mean())
        # floor on the deviation: a perfectly flat chat must not make every blip a peak
        desvio = max(float(passado.std()), 0.5, normal * 0.25)
        z = (media_recente - normal) / desvio

        if z < self.limiar_z or media_recente < self.min_msgs_s:
            return None
        if self._t - self._ultimo_pico < self.refratario_s:
            return None
        self._ultimo_pico = self._t
        return round(z, 2)

    def esquecer(self) -> None:
        """New stream or a long gap: start calibrating again."""
        self._hist.clear()
        self._ultimo_pico = -10**9
