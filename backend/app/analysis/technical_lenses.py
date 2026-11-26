"""The seven lenses the P05 Technical Agent reads a stock through.

Pure functions over an ascending run of daily bars. Nothing here opens a
database, and nothing here may import another engine: the PRD requires the
analytical isolation between P05 agents to be enforced by what the code can
reach, not by an instruction telling it not to look. A test asserts that.

Each lens always returns a reading. A lens with too little history says so
rather than returning a confident neutral, because "no evidence" and "evidence
of nothing" are different findings and only one of them is worth reporting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Sequence

from .indicators import DailyBar

REPORTED = "reported"
NO_MATERIAL_CHANGE = "no_material_change"
INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class LensReading:
    """One lens's finding. `status` separates silence from absence."""

    lens: str
    status: str
    direction: str = "neutral"          # positive / negative / neutral
    magnitude: str = "minor"            # minor / moderate / strong / exceptional
    confidence: str = "medium"          # low / medium / high
    persistence: str = "short"          # short / medium / long / structural
    summary: str = ""
    drivers: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    evidence: dict = field(default_factory=dict)


def _need(bars: Sequence[DailyBar], count: int, lens: str) -> LensReading | None:
    if len(bars) < count:
        return LensReading(
            lens=lens,
            status=INSUFFICIENT_DATA,
            summary=f"需要至少 {count} 根日线，当前只有 {len(bars)} 根。",
            evidence={"bars_available": len(bars), "bars_required": count},
        )
    return None


def _ma(values: Sequence[float], window: int) -> float | None:
    return mean(values[-window:]) if len(values) >= window else None


def _roc(values: Sequence[float], window: int) -> float | None:
    """Rate of change over `window` bars, as a percentage."""
    if len(values) <= window or values[-(window + 1)] <= 0:
        return None
    return (values[-1] / values[-(window + 1)] - 1) * 100


def trend(bars: Sequence[DailyBar]) -> LensReading:
    """Direction and quality of the trend, from moving-average stack and slope."""
    short = _need(bars, 60, "trend")
    if short:
        return short
    closes = [bar.close for bar in bars]
    ma20, ma50 = _ma(closes, 20), _ma(closes, 50)
    ma200 = _ma(closes, 200)
    close = closes[-1]
    # slope measured over half the window, so a flat MA does not read as a trend
    slope50 = (ma50 / mean(closes[-75:-25]) - 1) * 100 if len(closes) >= 75 else None

    up = [close > ma20, ma20 > ma50, (slope50 or 0) > 1.0]
    down = [close < ma20, ma20 < ma50, (slope50 or 0) < -1.0]
    if ma200 is not None:
        up.append(ma50 > ma200)
        down.append(ma50 < ma200)

    aligned_up, aligned_down = sum(up), sum(down)
    total = len(up)
    evidence = {"close": close, "ma20": ma20, "ma50": ma50, "ma200": ma200,
                "ma50_slope_pct": slope50, "aligned_up": aligned_up, "aligned_down": aligned_down}

    if aligned_up == total:
        return LensReading("trend", REPORTED, "positive", "strong" if total == 4 else "moderate",
                           "high" if total == 4 else "medium", "long",
                           f"均线完全多头排列，50 日均线 {slope50:+.1f}% 上行。",
                           (f"收盘价在 MA20 之上，MA20>MA50{'>MA200' if ma200 else ''}",),
                           ("均线排列是滞后信号，转折时反应慢",), evidence)
    if aligned_down == total:
        return LensReading("trend", REPORTED, "negative", "strong" if total == 4 else "moderate",
                           "high" if total == 4 else "medium", "long",
                           f"均线完全空头排列，50 日均线 {slope50:+.1f}% 下行。",
                           (f"收盘价在 MA20 之下，MA20<MA50{'<MA200' if ma200 else ''}",),
                           ("下跌趋势中反弹频繁，单日转强不构成反转",), evidence)
    return LensReading("trend", NO_MATERIAL_CHANGE, "neutral", "minor", "medium", "medium",
                       f"均线排列不一致（{aligned_up} 项偏多 / {aligned_down} 项偏空），趋势方向不明。",
                       evidence=evidence)


def momentum(bars: Sequence[DailyBar]) -> LensReading:
    """Speed of the move, and whether it is still accelerating."""
    short = _need(bars, 61, "momentum")
    if short:
        return short
    closes = [bar.close for bar in bars]
    roc10, roc20, roc60 = _roc(closes, 10), _roc(closes, 20), _roc(closes, 60)
    evidence = {"roc10_pct": roc10, "roc20_pct": roc20, "roc60_pct": roc60}

    # a long move whose recent leg has gone flat or negative is decelerating
    if roc60 is not None and roc60 > 20 and roc10 is not None and roc10 < 0:
        return LensReading("momentum", REPORTED, "negative", "moderate", "medium", "short",
                           f"60 日累计 {roc60:+.1f}%，但最近 10 日 {roc10:+.1f}% 转负，上行动能在减弱。",
                           ("长周期涨幅仍大，短周期已转负",),
                           ("动能减弱可能只是上升途中的休整，不等于反转",), evidence)
    if roc60 is not None and roc60 < -20 and roc10 is not None and roc10 > 0:
        return LensReading("momentum", REPORTED, "positive", "moderate", "medium", "short",
                           f"60 日累计 {roc60:+.1f}%，但最近 10 日 {roc10:+.1f}% 转正，下行动能在减弱。",
                           ("长周期跌幅仍大，短周期已转正",),
                           ("下跌中的反弹常见，需价格结构确认",), evidence)
    if roc20 is not None and abs(roc20) >= 25:
        positive = roc20 > 0
        return LensReading("momentum", REPORTED, "positive" if positive else "negative",
                           "strong" if abs(roc20) >= 50 else "moderate", "high", "short",
                           f"20 日累计 {roc20:+.1f}%，动量显著。",
                           (f"20 日涨跌幅 {roc20:+.1f}%",),
                           ("单一周期的强动量容易均值回归",), evidence)
    return LensReading("momentum", NO_MATERIAL_CHANGE, "neutral", "minor", "medium", "short",
                       f"动量平稳（20 日 {roc20:+.1f}%）。" if roc20 is not None else "动量平稳。",
                       evidence=evidence)


def participation(bars: Sequence[DailyBar]) -> LensReading:
    """Whether trading activity supports what the price is doing."""
    short = _need(bars, 21, "participation")
    if short:
        return short
    volumes = [bar.volume for bar in bars]
    closes = [bar.close for bar in bars]
    prior20 = volumes[-21:-1]
    avg20 = mean(prior20) if prior20 else 0
    rel_vol = volumes[-1] / avg20 if avg20 > 0 else None
    turnover = closes[-1] * volumes[-1]
    roc5 = _roc(closes, 5)
    vol_ma5 = mean(volumes[-5:])
    vol_trend = vol_ma5 / avg20 if avg20 > 0 else None
    evidence = {"rel_vol": rel_vol, "dollar_turnover": turnover,
                "volume_ma5_vs_ma20": vol_trend, "roc5_pct": roc5}

    if rel_vol is not None and rel_vol >= 3.0:
        return LensReading("participation", REPORTED,
                           "positive" if (roc5 or 0) >= 0 else "negative",
                           "exceptional" if rel_vol >= 8 else "strong", "high", "short",
                           f"成交量为 20 日均量的 {rel_vol:.1f} 倍。",
                           (f"相对成交量 {rel_vol:.1f}x",),
                           ("小盘股单日放量可能来自一笔大单，不代表持续参与",), evidence)
    # price advancing on steadily thinning volume: the move is losing sponsorship
    if roc5 is not None and roc5 > 5 and vol_trend is not None and vol_trend < 0.7:
        return LensReading("participation", REPORTED, "negative", "moderate", "medium", "short",
                           f"5 日价格 {roc5:+.1f}% 但量能萎缩至均量的 {vol_trend:.0%}，上涨缺乏承接。",
                           ("价格上行而成交量下行",),
                           ("缩量上涨可持续较久，不是即时卖出依据",), evidence)
    return LensReading("participation", NO_MATERIAL_CHANGE, "neutral", "minor", "medium", "short",
                       f"成交活跃度正常（相对量 {rel_vol:.1f}x）。" if rel_vol else "成交活跃度正常。",
                       evidence=evidence)


def volatility(bars: Sequence[DailyBar]) -> LensReading:
    """Contraction and expansion of the daily range."""
    short = _need(bars, 60, "volatility")
    if short:
        return short
    trs = []
    for prev, cur in zip(bars[-60:-1], bars[-59:]):
        trs.append(max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close)))
    atr14 = mean(trs[-14:])
    atr50 = mean(trs[-50:])
    close = bars[-1].close
    atr_pct = atr14 / close * 100 if close else None
    ratio = atr14 / atr50 if atr50 > 0 else None
    evidence = {"atr14": atr14, "atr50": atr50, "atr14_pct_of_close": atr_pct, "atr_ratio": ratio}

    if ratio is not None and ratio <= 0.65:
        return LensReading("volatility", REPORTED, "neutral", "moderate", "medium", "medium",
                           f"波动收缩：14 日 ATR 为 50 日的 {ratio:.0%}，区间趋紧。",
                           ("ATR 收缩，常出现在方向选择之前",),
                           ("收缩本身不指示方向，突破可能向下",), evidence)
    if ratio is not None and ratio >= 1.8:
        return LensReading("volatility", REPORTED, "neutral",
                           "strong" if ratio >= 2.5 else "moderate", "medium", "short",
                           f"波动放大：14 日 ATR 为 50 日的 {ratio:.0%}。",
                           ("ATR 快速扩张，风险与机会同时放大",),
                           ("波动放大期间止损更易被触发",), evidence)
    return LensReading("volatility", NO_MATERIAL_CHANGE, "neutral", "minor", "medium", "short",
                       f"波动水平正常（ATR 约为价格的 {atr_pct:.1f}%）。" if atr_pct else "波动水平正常。",
                       evidence=evidence)


def structure(bars: Sequence[DailyBar]) -> LensReading:
    """Where price sits inside its own range, and what it has to beat."""
    short = _need(bars, 60, "structure")
    if short:
        return short
    window = [bar.close for bar in bars[-60:]]
    low, high, close = min(window), max(window), window[-1]
    span = high - low
    position = (close - low) / span if span > 0 else None
    evidence = {"range_low_60": low, "range_high_60": high, "close": close,
                "position_in_range": position}

    if position is not None and position >= 0.9:
        return LensReading("structure", REPORTED, "positive", "moderate", "medium", "medium",
                           f"价格位于 60 日区间顶部 {position:.0%} 处，阻力位 {high:.3f}。",
                           (f"距 60 日高点 {(high / close - 1) * 100:.1f}%",),
                           ("区间顶部同时是阻力，未突破前属于被动位置",), evidence)
    if position is not None and position <= 0.1:
        return LensReading("structure", REPORTED, "negative", "moderate", "medium", "medium",
                           f"价格位于 60 日区间底部 {position:.0%} 处，支撑位 {low:.3f}。",
                           (f"距 60 日低点 {(close / low - 1) * 100:.1f}%",),
                           ("区间底部可能是支撑，也可能是下一段下跌的起点",), evidence)
    return LensReading("structure", NO_MATERIAL_CHANGE, "neutral", "minor", "medium", "medium",
                       f"价格位于 60 日区间 {position:.0%} 处，无结构性位置。" if position else "区间位置居中。",
                       evidence=evidence)


def breakout(bars: Sequence[DailyBar]) -> LensReading:
    """New highs and lows, and breakouts that did not hold."""
    short = _need(bars, 61, "breakout")
    if short:
        return short
    closes = [bar.close for bar in bars]
    close = closes[-1]
    prior60_high, prior60_low = max(closes[-61:-1]), min(closes[-61:-1])
    prior252_high = max(closes[-253:-1]) if len(closes) >= 253 else None
    evidence = {"close": close, "prior_high_60": prior60_high, "prior_low_60": prior60_low,
                "prior_high_252": prior252_high}

    if prior252_high is not None and close > prior252_high:
        # Direction stays neutral on purpose. This project's own backtest
        # measured -29.78% excess return past five days for a new 252-day high,
        # and a rule the evidence does not support must not be able to supply
        # the second opinion that turns a single reading into a confirmation.
        return LensReading("breakout", REPORTED, "neutral", "moderate", "low", "medium",
                           f"收于 252 日新高 {close:.3f}（仅作关注）。",
                           ("突破年内高点",),
                           ("该规则在本项目回测中未获支持，仅作关注，不计入方向确认",), evidence)
    if close > prior60_high:
        return LensReading("breakout", REPORTED, "positive", "moderate", "high", "short",
                           f"收于 60 日新高 {close:.3f}，前高 {prior60_high:.3f}。",
                           ("突破 60 日高点",), ("突破后回落是常见的失败形态",), evidence)
    if close < prior60_low:
        return LensReading("breakout", REPORTED, "negative", "moderate", "high", "short",
                           f"收于 60 日新低 {close:.3f}，前低 {prior60_low:.3f}。",
                           ("跌破 60 日低点",), ("新低后超跌反弹常见",), evidence)
    # a high made in the last ten sessions that price has since fallen back under
    recent = closes[-10:]
    before_recent = closes[-70:-10]
    if before_recent and max(recent) > max(before_recent) and close < max(before_recent):
        return LensReading("breakout", REPORTED, "negative", "moderate", "medium", "short",
                           f"十日内曾创新高 {max(recent):.3f}，现已跌回前高 {max(before_recent):.3f} 之下。",
                           ("突破未能守住",), ("假突破也可能在数日后重新站上",), evidence)
    return LensReading("breakout", NO_MATERIAL_CHANGE, "neutral", "minor", "medium", "short",
                       "未触及 60 日高低点，无突破或跌破。", evidence=evidence)


def exhaustion(bars: Sequence[DailyBar]) -> LensReading:
    """How far the move has stretched from its own base, and whether it is tiring."""
    short = _need(bars, 60, "exhaustion")
    if short:
        return short
    closes = [bar.close for bar in bars]
    close = closes[-1]
    ma20 = _ma(closes, 20)
    extension = (close / ma20 - 1) * 100 if ma20 else None
    # how unusual that stretch is for this stock, rather than a fixed threshold
    history = [(closes[i] / mean(closes[i - 19:i + 1]) - 1) * 100
               for i in range(19, len(closes))]
    typical = mean(abs(value) for value in history[-60:]) if len(history) >= 60 else None
    up_days = 0
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] > closes[i - 1]:
            up_days += 1
        else:
            break
    evidence = {"extension_above_ma20_pct": extension, "typical_abs_extension_pct": typical,
                "consecutive_up_days": up_days}

    if extension is not None and typical and extension > typical * 2.5:
        return LensReading("exhaustion", REPORTED, "negative",
                           "strong" if extension > typical * 4 else "moderate", "medium", "short",
                           f"偏离 20 日均线 {extension:+.1f}%，为该股常态偏离（{typical:.1f}%）的 "
                           f"{extension / typical:.1f} 倍。",
                           ("价格过度延伸，回归均线的压力上升",),
                           ("强势股可以长时间维持极端偏离，不等于见顶",), evidence)
    if up_days >= 7:
        return LensReading("exhaustion", REPORTED, "negative", "moderate", "low", "short",
                           f"连续 {up_days} 个交易日收阳，短期透支。",
                           (f"连涨 {up_days} 日",),
                           ("连涨天数本身预测力弱，需结合量能与位置",), evidence)
    return LensReading("exhaustion", NO_MATERIAL_CHANGE, "neutral", "minor", "medium", "short",
                       f"偏离 20 日均线 {extension:+.1f}%，未见过度延伸。" if extension is not None
                       else "未见过度延伸。", evidence=evidence)


LENSES = (trend, momentum, participation, volatility, structure, breakout, exhaustion)


def read_all(bars: Sequence[DailyBar]) -> list[LensReading]:
    """Every lens, in the order the PRD lists them."""
    return [lens(bars) for lens in LENSES]
