"""Diario de operaciones persistente (CSV) + métricas acumuladas."""
from __future__ import annotations
import csv
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JOURNAL_PATH = ROOT / "journal" / "trades.csv"
FIELDS = ["fecha", "symbol", "evento", "lado", "qty", "precio", "fee",
          "pnl", "prob", "confianza", "modo", "nota"]


def log_trade(row: dict) -> None:
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {**{k: "" for k in FIELDS}, **row}
    # C4: 'fecha' ya existe (vacía) en el dict base, así que setdefault no actúa.
    # Forzar timestamp UTC si viene vacía.
    if not row.get("fecha"):
        row["fecha"] = datetime.now(timezone.utc).isoformat()
    new = not JOURNAL_PATH.exists()
    with open(JOURNAL_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in FIELDS})


def _closed_pnls(rows) -> list[float]:
    out = []
    for r in rows:
        if r.get("evento") == "close" and r.get("pnl") not in ("", None):
            try:
                out.append(float(r["pnl"]))
            except ValueError:
                pass
    return out


def metrics() -> dict:
    if not JOURNAL_PATH.exists():
        return {"trades": 0, "win_rate": 0.0, "pnl_total": 0.0, "wins": 0, "losses": 0}
    with open(JOURNAL_PATH, newline="", encoding="utf-8") as f:
        pnls = _closed_pnls(list(csv.DictReader(f)))
    if not pnls:
        return {"trades": 0, "win_rate": 0.0, "pnl_total": 0.0, "wins": 0, "losses": 0}
    wins = sum(1 for p in pnls if p > 0)
    return {"trades": len(pnls), "win_rate": round(wins / len(pnls) * 100, 1),
            "pnl_total": round(sum(pnls), 2), "wins": wins, "losses": len(pnls) - wins}


def today_pnl(now: datetime | None = None) -> float:
    """PnL realizado HOY (UTC). Negativo si pérdida. Usado por el kill-switch (C2)."""
    if not JOURNAL_PATH.exists():
        return 0.0
    today = (now or datetime.now(timezone.utc)).date().isoformat()
    total = 0.0
    with open(JOURNAL_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("evento") != "close":
                continue
            fecha = (r.get("fecha") or "")
            if not fecha.startswith(today):
                continue
            try:
                total += float(r.get("pnl") or 0)
            except ValueError:
                pass
    return total
