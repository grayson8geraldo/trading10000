from strategies.scalp_momentum import ScalpMomentumStrategy
from strategies.breakout_volume import BreakoutVolumeStrategy
from strategies.trend_follow import TrendFollowStrategy
from strategies.mean_revert import MeanRevertStrategy
from strategies.swing import SwingStrategy

STRATEGY_MAP = {
    "scalp_momentum": ScalpMomentumStrategy,
    "breakout_volume": BreakoutVolumeStrategy,
    "trend_follow": TrendFollowStrategy,
    "mean_revert": MeanRevertStrategy,
    "swing": SwingStrategy,
}
