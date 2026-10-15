"""Numerical frequency-domain analysis for sampled real signals.

This module has no GUI dependencies and does not modify the source arrays.
"""

import numpy as np


def amplitude_spectrum(time, signal, *, window="hann", detrend="mean",
                       missing="raise", sampling="raise", sampling_rtol=1e-3,
                       return_info=False):
    """Return one-sided FFT frequencies (Hz) and amplitudes.

    Times must be strictly increasing seconds; signal values must be real.
    At least three observations are required. By default, irregular sample
    spacing and missing values raise ValueError. With
    ``sampling='interpolate'``, irregular observations are interpolated onto
    an evenly spaced time grid. Its spacing is inferred from the median
    observed spacing; no sampling rate can be inferred from absent data.
    With ``missing='interpolate'``, interior NaNs are filled linearly.
    Missing endpoints cannot be inferred and are rejected.

    ``return_info=True`` adds a dictionary of resampling details as a third
    return value. The input arrays are never modified.

    The default periodic Hann window is normalized by its coherent gain so
    bin-centered sinusoids retain their amplitude. DC and Nyquist bins are
    not doubled. Linear interpolation may attenuate high frequencies across
    missing intervals, especially long gaps.
    """
    if window not in ("hann", "rectangular"):
        raise ValueError("window must be 'hann' or 'rectangular'")
    if detrend not in ("mean", "none"):
        raise ValueError("detrend must be 'mean' or 'none'")
    if missing not in ("raise", "interpolate"):
        raise ValueError("missing must be 'raise' or 'interpolate'")
    if sampling not in ("raise", "interpolate"):
        raise ValueError("sampling must be 'raise' or 'interpolate'")
    if not np.isfinite(sampling_rtol) or not 0 <= sampling_rtol < 1:
        raise ValueError("sampling_rtol must be finite and in [0, 1)")

    for name, values in (("time", time), ("signal", signal)):
        if np.iscomplexobj(values):
            raise ValueError(f"{name} must contain real values")

    try:
        timestamps = np.asarray(time, dtype=np.float64)
        samples = np.asarray(signal, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("time and signal must contain numeric values") from exc

    if timestamps.ndim != 1 or samples.ndim != 1:
        raise ValueError("time and signal must be one-dimensional")
    if timestamps.size != samples.size:
        raise ValueError("time and signal must have the same number of samples")
    if timestamps.size < 3:
        raise ValueError("at least three samples are required")
    if not np.all(np.isfinite(timestamps)):
        raise ValueError("time contains nonfinite values")

    intervals = np.diff(timestamps)
    if not np.all(intervals > 0):
        raise ValueError("time must be strictly increasing")
    sample_period = float(np.median(intervals))
    irregular = np.any(np.abs(intervals - sample_period)
                       > sampling_rtol * sample_period)
    if irregular and sampling == "raise":
        raise ValueError("time samples are not uniformly spaced; use "
                         "sampling='interpolate' to resample")

    if np.any(np.isinf(samples)):
        raise ValueError("signal contains infinite values")
    nan_mask = np.isnan(samples)
    filled_missing = bool(np.any(nan_mask))
    if np.any(nan_mask):
        if missing == "raise":
            raise ValueError("signal contains missing samples; use "
                             "missing='interpolate' to fill internal NaNs")
        if nan_mask[0] or nan_mask[-1]:
            raise ValueError("cannot interpolate missing edge samples")
        samples = np.interp(timestamps, timestamps[~nan_mask],
                            samples[~nan_mask])

    if irregular:
        # Preserve both observed endpoints, with nearly the median spacing.
        # Bounding grid length prevents large data gaps from allocating an
        # impractically large array during interactive plotting.
        estimated_intervals = ((timestamps[-1] - timestamps[0])
                               / sample_period)
        if (not np.isfinite(estimated_intervals)
                or estimated_intervals >= 2_000_000):
            raise ValueError("interpolation would require too many samples; "
                             "choose a shorter time interval")
        points = int(np.rint(estimated_intervals)) + 1
        if points > 2_000_000:
            raise ValueError("interpolation would require too many samples; "
                             "choose a shorter time interval")
        if points < 3:
            raise ValueError("interpolation would produce fewer than three "
                             "samples")
        uniform_times = np.linspace(timestamps[0], timestamps[-1], points)
        samples = np.interp(uniform_times, timestamps, samples)
        sample_period = float((uniform_times[-1] - uniform_times[0])
                              / (points - 1))

    if detrend == "mean":
        samples = samples - np.mean(samples)
    if window == "hann":
        # Periodic Hann is appropriate for DFT analysis. Unlike the
        # symmetric Hann, it has an exact coherent gain of 0.5.
        weights = np.hanning(samples.size + 1)[:-1]
    else:
        weights = np.ones(samples.size, dtype=np.float64)

    transformed = np.fft.rfft(samples * weights)
    amplitudes = 2.0 * np.abs(transformed) / np.sum(weights)
    amplitudes[0] *= 0.5
    if samples.size % 2 == 0:
        amplitudes[-1] *= 0.5
    frequencies = np.fft.rfftfreq(samples.size, d=sample_period)
    if return_info:
        return frequencies, amplitudes, {
            "resampled": bool(irregular),
            "interpolated_missing": filled_missing,
            "sample_period": sample_period,
            "sample_count": samples.size,
        }
    return frequencies, amplitudes


def select_time_interval(time, signal, limits):
    """Return samples inside the inclusive, currently visible time limits.

    The original arrays remain unchanged. The FFT implementation validates
    monotonicity and uniformity of the selected timestamps afterwards.
    """
    if len(limits) != 2 or not np.all(np.isfinite(limits)):
        raise ValueError("visible time limits must be finite")
    timestamps = np.asarray(time)
    samples = np.asarray(signal)
    lower, upper = sorted(limits)
    selected = (timestamps >= lower) & (timestamps <= upper)
    if np.count_nonzero(selected) < 3:
        raise ValueError("visible time range contains fewer than three samples")
    return timestamps[selected], samples[selected]


def limit_spectrum_frequencies(frequencies, amplitudes, minimum=0.0,
                               maximum=None):
    """Restrict an amplitude spectrum to an inclusive frequency interval."""
    if not np.isfinite(minimum) or minimum < 0:
        raise ValueError("minimum frequency must be finite and nonnegative")
    if maximum is not None and (not np.isfinite(maximum)
                                or maximum <= minimum):
        raise ValueError("maximum frequency must exceed minimum frequency")
    selected = frequencies >= minimum
    if maximum is not None:
        selected &= frequencies <= maximum
    if not np.any(selected):
        raise ValueError("frequency range contains no FFT bins")
    return frequencies[selected], amplitudes[selected]


def spectrum_decibels(amplitudes, floor_db=-120.0):
    """Return dB relative to the spectrum's largest amplitude (0 dB).

    The floor avoids negative infinity for zero-valued FFT bins. Spectra
    without any nonzero magnitude cannot be normalized to a peak.
    """
    values = np.asarray(amplitudes, dtype=float)
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError("amplitudes must be a finite one-dimensional array")
    if not np.isfinite(floor_db) or floor_db >= 0:
        raise ValueError("floor_db must be finite and negative")
    if np.any(values < 0):
        raise ValueError("amplitudes must be nonnegative")
    peak = float(np.max(values)) if values.size else 0.0
    if peak == 0:
        raise ValueError("zero spectrum has no dB reference peak")
    clipped = np.maximum(values / peak, 10 ** (floor_db / 20))
    return 20.0 * np.log10(clipped)
