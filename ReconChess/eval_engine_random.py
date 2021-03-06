import base as base
import chess
import numpy as np
from typing import List


class RandomEvaluationEngine(base.SimulationEngine):
    def score_boards(self, boards: List[chess.Board]) -> np.ndarray:
        return (np.random.randn(len(boards)) - 0.5) * 100

    def evaluate_rewards(self, boards: List[chess.Board]) -> np.ndarray:
        return np.zeros(len(boards))
