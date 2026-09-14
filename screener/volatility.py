"""
Forecast volatilitas harga pakai GARCH(1,1) (library `arch`, satu ekosistem
dengan statsmodels).

PENTING: INI BUKAN FORECAST HARGA. Ini forecast SEBERAPA LEBAR kemungkinan
pergerakan harga ke depan (band 95%), bukan tebakan harga pasti. Dipakai
sebagai referensi risk sizing / lebar stop-loss, bukan sinyal beli/jual.
"""
import numpy as np
import pandas as pd
from arch import arch_model


def forecast_volatility(df: pd.DataFrame, horizon: int = 10) -> dict:
    """
    df: dataframe harga harian (butuh kolom 'Close'), minimal ~120 baris.
    Return dict siap-export ke JSON. Kalau data kurang/model gagal fit,
    return status gagal (JANGAN raise, biar batch tidak berhenti).
    """
    closes = df["Close"].dropna()
    if len(closes) < 120:
        return {"status": "insufficient_data"}

    prices = closes.tail(500).values
    dates = closes.tail(500).index
    returns = 100 * np.diff(np.log(prices))

    try:
        am = arch_model(returns, vol="Garch", p=1, q=1, dist="normal", rescale=False)
        res = am.fit(disp="off")
    except Exception as e:
        return {"status": "fit_failed", "error": str(e)}

    fc = res.forecast(horizon=horizon, reindex=False)
    variance_forecast = fc.variance.values[-1]
    daily_vol_pct = np.sqrt(variance_forecast)
    cum_vol_pct = np.sqrt(np.cumsum(variance_forecast))

    last_price = float(prices[-1])
    upper_band = [round(last_price * np.exp(1.96 * cv / 100), 2) for cv in cum_vol_pct]
    lower_band = [round(last_price * np.exp(-1.96 * cv / 100), 2) for cv in cum_vol_pct]

    hist_vol_60d = float(returns[-60:].std()) if len(returns) >= 60 else float(returns.std())
    current_forecast_vol = float(daily_vol_pct[0])

    regime = "tinggi" if current_forecast_vol > hist_vol_60d * 1.2 else \
             "rendah" if current_forecast_vol < hist_vol_60d * 0.8 else "normal"

    price_history = [
        {"date": d.strftime("%Y-%m-%d"), "close": round(float(p), 2)}
        for d, p in zip(dates[-90:], prices[-90:])
    ]

    return {
        "status": "ok",
        "last_price": last_price,
        "last_date": dates[-1].strftime("%Y-%m-%d"),
        "price_history": price_history,
        "daily_vol_forecast_pct": [round(float(v), 3) for v in daily_vol_pct],
        "upper_band_95": upper_band,
        "lower_band_95": lower_band,
        "hist_vol_60d_pct": round(hist_vol_60d, 3),
        "current_forecast_vol_pct": round(current_forecast_vol, 3),
        "regime": regime,
    }
