"""Numerical frequency-domain analysis for regularly sampled real signals.

This module has no GUI dependencies and does not modify the source arrays.
"""

import numpy as np


def amplitude_spectrum(time, signal, *, window="hann", detrend="mean",
                       missing="raise", sampling_rtol=1e-3):
    """Return (frequencies_hz, amplitudes) for a one-sided real FFT.

    ``time`` contains strictly increasing times in seconds, with nearly
    uniform spacing. ``signal`` contains real samples in their original
    physical units. Both must have the same one-dimensional length (>= 3).

    The default Hann window is periodic, and amplitudes are normalized by
    its coherent gain. This preserves the amplitude of bin-centered tones.
    The zero-frequency and (for even sample counts) Nyquist bins are not
    doubled. Frequency resolution is approximately 1 / (N * sample_period).

    ``detrend`` may be 'mean' or 'none'. ``window`` may be 'hann' or
    'rectangular'. Missing signal samples are rejected by default; set
    ``missing='interpolate'`` to linearly fill internal NaNs. Missing edge
    samples, nonfinite timestamps, and irregular sample times are rejected.
    The function does not silently resample irregular timestamps.
    """
    if window not in ("hann", "rectangular"):
        raise ValueError("window must be 'hann' or 'rectangular'")
    if detrend not in ("mean", "none"):
        raise ValueError("detrend must be 'mean' or 'none'")
    if missing not in ("raise", "interpolate"):
        raise ValueError("missing must be 'raise' or 'interpolate'")
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
    if np.any(np.abs(intervals - sample_period)
              > sampling_rtol * sample_period):
        raise ValueError("time samples are not uniformly spaced; resample "
                         "before using the FFT")

    if np.any(np.isinf(samples)):
        raise ValueError("signal contains infinite values")
    nan_mask = np.isnan(samples)
    if np.any(nan_mask):
        if missing == "raise":
            raise ValueError("signal contains missing samples; use "
                             "missing='interpolate' to fill internal NaNs")
        if nan_mask[0] or nan_mask[-1]:
            raise ValueError("cannot interpolate missing edge samples")
        samples = np.interp(timestamps, timestamps[~nan_mask],
                            samples[~nan_mask])

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
    return frequencies, amplitudes
