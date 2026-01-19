"""Fetch top 100 spot instruments by 24h quote volume and save 3Y daily candles."""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List

from okx import MarketData


OUTPUT_DIR = Path("data/top100_history")
TOP_N = 100
BAR = "1D"
REQUEST_LIMIT = "100"
SLEEP_SECONDS = 0.2


@dataclass(frozen=True)
class Candle:
    ts: int
    open: str
    high: str
    low: str
    close: str
    volume: str
    volume_ccy: str
    volume_quote: str
    confirm: str


def _parse_candles(raw: Iterable[List[str]]) -> List[Candle]:
    candles = []
    for row in raw:
        if len(row) < 9:
            continue
        candles.append(
            Candle(
                ts=int(row[0]),
                open=row[1],
                high=row[2],
                low=row[3],
                close=row[4],
                volume=row[5],
                volume_ccy=row[6],
                volume_quote=row[7],
                confirm=row[8],
            )
        )
    return candles


def _write_candles_csv(path: Path, candles: Iterable[Candle]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "ts",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "volume_ccy",
                "volume_quote",
                "confirm",
            ]
        )
        for candle in candles:
            writer.writerow(
                [
                    candle.ts,
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                    candle.volume_ccy,
                    candle.volume_quote,
                    candle.confirm,
                ]
            )


def fetch_top_spot_by_volume(api: MarketData.MarketAPI, top_n: int) -> List[dict]:
    response = api.get_tickers(instType="SPOT")
    data = response.get("data", []) if isinstance(response, dict) else []
    ranked = sorted(
        data,
        key=lambda item: float(item.get("volCcy24h", 0) or 0),
        reverse=True,
    )
    return ranked[:top_n]


def fetch_history_3y(api: MarketData.MarketAPI, inst_id: str) -> List[Candle]:
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=365 * 3)
    start_ms = int(start_time.timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)

    candles: List[Candle] = []
    while True:
        response = api.get_history_candlesticks(
            instId=inst_id,
            before=str(end_ms),
            bar=BAR,
            limit=REQUEST_LIMIT,
        )
        raw = response.get("data", []) if isinstance(response, dict) else []
        if not raw:
            break
        batch = _parse_candles(raw)
        if not batch:
            break
        candles.extend(batch)
        oldest = min(candle.ts for candle in batch)
        if oldest <= start_ms:
            break
        end_ms = oldest - 1
        time.sleep(SLEEP_SECONDS)

    filtered = [candle for candle in candles if candle.ts >= start_ms]
    filtered.sort(key=lambda candle: candle.ts)
    return filtered


def main() -> None:
    api = MarketData.MarketAPI()
    top_assets = fetch_top_spot_by_volume(api, TOP_N)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "top100_assets.json").write_text(
        json.dumps(top_assets, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for asset in top_assets:
        inst_id = asset.get("instId")
        if not inst_id:
            continue
        candles = fetch_history_3y(api, inst_id)
        if candles:
            output_path = OUTPUT_DIR / f"{inst_id.replace('/', '-')}.csv"
            _write_candles_csv(output_path, candles)


if __name__ == "__main__":
    main()
