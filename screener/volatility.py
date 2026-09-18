"""
Forecast volatilitas harga menggunakan GARCH(1,1).

Fitur:
- GARCH untuk seluruh ticker yang memiliki cukup data
- Batas iterasi adaptif: 150, lalu 500 jika belum konvergen
- Pemrosesan paralel menggunakan ProcessPoolExecutor
- Hasil disiapkan untuk web/dashboard_data.json
"""

from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp

import numpy as np
import pandas as pd
from arch import arch_model


MINIMUM_OBSERVATIONS = 120
MAXIMUM_OBSERVATIONS = 500
HISTORICAL_VOLATILITY_WINDOW = 60


def _fit_model(
    returns: np.ndarray,
    max_iterations: int,
):
    """
    Fit model GARCH(1,1).

    maxiter harus dikirim melalui parameter options, bukan sebagai
    keyword langsung ke ARCHModel.fit().
    """
    model = arch_model(
        returns,
        mean="Constant",
        vol="GARCH",
        p=1,
        q=1,
        dist="normal",
        rescale=False,
    )

    return model.fit(
        disp="off",
        update_freq=0,
        show_warning=False,
        options={"maxiter": max_iterations},
    )


def _fit_garch(
    returns: np.ndarray,
    horizon: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Fit GARCH dengan batas iterasi adaptif.

    Percobaan pertama memakai 150 iterasi. Jika optimizer belum
    konvergen, model dijalankan kembali dengan maksimal 500 iterasi.
    """
    result = _fit_model(returns, max_iterations=150)

    if result.convergence_flag != 0:
        result = _fit_model(returns, max_iterations=500)

    if result.convergence_flag != 0:
        raise RuntimeError(
            "Model GARCH tidak berhasil konvergen setelah 500 iterasi."
        )

    forecast = result.forecast(
        horizon=horizon,
        reindex=False,
    )

    variance = np.asarray(
        forecast.variance.values[-1],
        dtype=float,
    )

    if len(variance) != horizon:
        raise RuntimeError(
            f"Jumlah hasil forecast tidak sesuai: "
            f"diharapkan {horizon}, diperoleh {len(variance)}."
        )

    if not np.all(np.isfinite(variance)):
        raise RuntimeError(
            "Forecast GARCH menghasilkan variance non-finite."
        )

    # Hindari error numerik berupa variance negatif sangat kecil.
    variance = np.maximum(variance, 0.0)

    daily_volatility = np.sqrt(variance)
    cumulative_volatility = np.sqrt(np.cumsum(variance))

    return daily_volatility, cumulative_volatility


def _build_result(
    prices: np.ndarray,
    dates: pd.Index,
    returns: np.ndarray,
    daily_volatility: np.ndarray,
    cumulative_volatility: np.ndarray,
) -> dict:
    """
    Susun hasil forecast agar siap diekspor ke dashboard.
    """
    last_price = float(prices[-1])

    upper_band = [
        round(
            last_price * np.exp(1.96 * volatility / 100),
            2,
        )
        for volatility in cumulative_volatility
    ]

    lower_band = [
        round(
            last_price * np.exp(-1.96 * volatility / 100),
            2,
        )
        for volatility in cumulative_volatility
    ]

    historical_returns = returns[
        -HISTORICAL_VOLATILITY_WINDOW:
    ]

    historical_volatility = float(
        np.std(historical_returns, ddof=1)
    )

    current_forecast = float(daily_volatility[0])

    if historical_volatility <= 0:
        regime = "normal"
    elif current_forecast > historical_volatility * 1.2:
        regime = "tinggi"
    elif current_forecast < historical_volatility * 0.8:
        regime = "rendah"
    else:
        regime = "normal"

    return {
        "status": "ok",
        "last_price": round(last_price, 2),
        "last_date": dates[-1].strftime("%Y-%m-%d"),
        "price_history": [
            {
                "date": date.strftime("%Y-%m-%d"),
                "close": round(float(price), 2),
            }
            for date, price in zip(
                dates[-90:],
                prices[-90:],
            )
        ],
        "daily_vol_forecast_pct": [
            round(float(value), 3)
            for value in daily_volatility
        ],
        "upper_band_95": upper_band,
        "lower_band_95": lower_band,
        "hist_vol_60d_pct": round(
            historical_volatility,
            3,
        ),
        "current_forecast_vol_pct": round(
            current_forecast,
            3,
        ),
        "regime": regime,
    }


def forecast_volatility(
    df: pd.DataFrame,
    horizon: int = 10,
) -> dict:
    """
    Forecast volatilitas satu saham.

    Mengembalikan status gagal sebagai dictionary agar kegagalan satu
    ticker tidak menghentikan seluruh proses screening.
    """
    try:
        if "Close" not in df.columns:
            return {
                "status": "invalid_data",
                "error": "Kolom Close tidak ditemukan.",
            }

        closes = pd.to_numeric(
            df["Close"],
            errors="coerce",
        ).dropna()

        # Log-return hanya valid untuk harga positif.
        closes = closes[closes > 0]

        if len(closes) < MINIMUM_OBSERVATIONS:
            return {
                "status": "insufficient_data",
                "observations": int(len(closes)),
                "minimum_required": MINIMUM_OBSERVATIONS,
            }

        closes = closes.tail(MAXIMUM_OBSERVATIONS)

        prices = closes.to_numpy(dtype=float)
        dates = closes.index

        returns = 100 * np.diff(np.log(prices))
        returns = returns[np.isfinite(returns)]

        if len(returns) < MINIMUM_OBSERVATIONS - 1:
            return {
                "status": "insufficient_data",
                "observations": int(len(returns)),
                "minimum_required": (
                    MINIMUM_OBSERVATIONS - 1
                ),
            }

        daily_volatility, cumulative_volatility = (
            _fit_garch(
                returns=returns,
                horizon=horizon,
            )
        )

        return _build_result(
            prices=prices,
            dates=dates,
            returns=returns,
            daily_volatility=daily_volatility,
            cumulative_volatility=cumulative_volatility,
        )

    except Exception as error:
        return {
            "status": "fit_failed",
            "error": (
                f"{type(error).__name__}: {error}"
            ),
        }


def _worker(
    task: tuple[str, pd.DataFrame, int],
) -> tuple[str, dict]:
    """
    Worker harus berada di tingkat modul agar dapat diproses oleh
    multiprocessing.
    """
    ticker, dataframe, horizon = task

    result = forecast_volatility(
        dataframe,
        horizon=horizon,
    )

    return ticker, result


def forecast_volatility_batch(
    items: list[tuple[str, pd.DataFrame]],
    horizon: int = 10,
    max_workers: int | None = None,
) -> dict[str, dict]:
    """
    Jalankan forecast GARCH secara paralel untuk banyak ticker.
    """
    if not items:
        return {}

    worker_count = max_workers or min(
        mp.cpu_count(),
        len(items),
    )

    worker_count = max(1, worker_count)

    tasks = [
        (ticker, dataframe, horizon)
        for ticker, dataframe in items
    ]

    results: dict[str, dict] = {}

    with ProcessPoolExecutor(
        max_workers=worker_count
    ) as executor:
        for ticker, volatility in executor.map(
            _worker,
            tasks,
        ):
            results[ticker] = volatility

    return results
