"""FFT amplitude, sampling, missing-data, and validation regression tests."""

import unittest

import numpy as np

from csv_plotter_fft import (
    amplitude_spectrum, limit_spectrum_frequencies, select_time_interval,
    spectrum_decibels,
)


class AmplitudeSpectrumTests(unittest.TestCase):
    def test_hann_bin_centered_sine_preserves_amplitude(self):
        count = 1024
        sample_period = 0.25
        times = 10000.0 + sample_period * np.arange(count)
        frequency = 64 / (count * sample_period)
        signal = 7.0 + 2.5 * np.sin(2 * np.pi * frequency * (times - times[0]))
        frequencies, amplitudes = amplitude_spectrum(times, signal)
        self.assertEqual(len(frequencies), count // 2 + 1)
        self.assertAlmostEqual(frequencies[64], frequency)
        self.assertAlmostEqual(amplitudes[64], 2.5, places=10)
        self.assertAlmostEqual(amplitudes[0], 0.0, places=10)

    def test_two_tones_with_different_amplitudes(self):
        count = 1000
        times = np.arange(count, dtype=float)
        signal = (3.0 * np.sin(2 * np.pi * 45 * times / count)
                  + 0.8 * np.cos(2 * np.pi * 117 * times / count))
        frequencies, amplitudes = amplitude_spectrum(times, signal)
        self.assertAlmostEqual(frequencies[45], 0.045)
        self.assertAlmostEqual(amplitudes[45], 3.0, places=10)
        self.assertAlmostEqual(amplitudes[117], 0.8, places=10)

    def test_rectangular_window_and_dc(self):
        count = 1001
        times = np.arange(count) / 10.0
        signal = 4.25 + 2.0 * np.cos(2 * np.pi * 31 * np.arange(count) / count)
        _, amplitudes = amplitude_spectrum(times, signal, window="rectangular",
                                           detrend="none")
        self.assertAlmostEqual(amplitudes[0], 4.25, places=10)
        self.assertAlmostEqual(amplitudes[31], 2.0, places=10)

    def test_even_nyquist_bin_is_not_doubled(self):
        count = 1000
        times = 0.25 * np.arange(count)
        signal = 1.7 * (-1.0) ** np.arange(count)
        frequencies, amplitudes = amplitude_spectrum(times, signal,
                                                     window="rectangular")
        self.assertAlmostEqual(frequencies[-1], 2.0)
        self.assertAlmostEqual(amplitudes[-1], 1.7, places=10)

    def test_constant_signal_zero_after_mean_removal(self):
        times = np.arange(128, dtype=float)
        _, amplitudes = amplitude_spectrum(times, np.full(128, 8.0))
        np.testing.assert_allclose(amplitudes, 0.0, atol=1e-12)

    def test_spectral_leakage_reduced_by_hann(self):
        count = 1024
        times = np.arange(count, dtype=float)
        signal = np.sin(2 * np.pi * 42.5 * times / count)
        _, rectangular = amplitude_spectrum(times, signal, window="rectangular")
        _, hann = amplitude_spectrum(times, signal, window="hann")
        self.assertLess(np.sum(hann[5:30] ** 2),
                        np.sum(rectangular[5:30] ** 2) * 0.01)

    def test_missing_signal_samples_can_be_interpolated(self):
        times = np.arange(100, dtype=float)
        signal = 1.0 + 0.5 * times
        expected = amplitude_spectrum(times, signal)
        signal[30:34] = np.nan
        with self.assertRaisesRegex(ValueError, "missing samples"):
            amplitude_spectrum(times, signal)
        actual = amplitude_spectrum(times, signal, missing="interpolate")
        np.testing.assert_allclose(actual[0], expected[0])
        np.testing.assert_allclose(actual[1], expected[1], atol=1e-12)

    def test_missing_edge_samples_are_rejected(self):
        times = np.arange(30, dtype=float)
        for index in (0, -1):
            with self.subTest(index=index):
                signal = np.ones(30)
                signal[index] = np.nan
                with self.assertRaisesRegex(ValueError, "edge"):
                    amplitude_spectrum(times, signal, missing="interpolate")

    def test_missing_and_irregular_time_samples_are_rejected(self):
        times = np.arange(30, dtype=float)
        signal = np.ones(30)
        for bad_times, message in (
                (np.where(times == 6, np.nan, times), "nonfinite"),
                (np.where(times == 6, 6.5, times), "not uniformly"),
                (np.where(times == 6, 5.0, times), "strictly increasing"),
                (times[::-1], "strictly increasing")):
            with self.subTest(message=message, times=bad_times[6]):
                with self.assertRaisesRegex(ValueError, message):
                    amplitude_spectrum(bad_times, signal)

    def test_small_timing_jitter_within_tolerance(self):
        times = np.arange(1001, dtype=float)
        times[1:-1] += 0.0001 * np.sin(np.arange(1, 1000))
        frequencies, _ = amplitude_spectrum(times, np.ones(times.size))
        self.assertAlmostEqual(frequencies[1], 1 / 1001, places=8)

    def test_invalid_options_and_input_shapes(self):
        times = np.arange(20, dtype=float)
        signal = np.ones(20)
        invalid_options = (
            (dict(window="blackman"), "window"),
            (dict(detrend="linear"), "detrend"),
            (dict(missing="drop"), "missing"),
            (dict(sampling_rtol=-0.1), "sampling_rtol"),
            (dict(sampling_rtol=float("nan")), "sampling_rtol"),
        )
        for kwargs, message in invalid_options:
            with self.subTest(kwargs=kwargs):
                with self.assertRaisesRegex(ValueError, message):
                    amplitude_spectrum(times, signal, **kwargs)
        bad_data = (
            (times, signal[:-1], "same number"),
            (times[:2], signal[:2], "at least three"),
            (times.reshape(4, 5), signal, "one-dimensional"),
            (times, signal.astype(complex), "real values"),
            (times, np.full(20, np.inf), "infinite"),
        )
        for time, values, message in bad_data:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    amplitude_spectrum(time, values)

    def test_time_range_selection_keeps_inputs_unchanged(self):
        times = 10000 + np.arange(400, dtype=float)
        signal = np.sin(times)
        original = signal.copy()
        selected_time, selected_signal = select_time_interval(
            times, signal, (10199.0, 10000.0))
        self.assertEqual(selected_time.size, 200)
        self.assertAlmostEqual(selected_time[-1], 10199)
        np.testing.assert_array_equal(signal, original)
        with self.assertRaisesRegex(ValueError, "fewer than three"):
            select_time_interval(times, signal, (10000, 10001))
        with self.assertRaisesRegex(ValueError, "finite"):
            select_time_interval(times, signal, (np.nan, 10020))

    def test_frequency_limits_and_validation(self):
        frequencies = np.arange(10, dtype=float) / 10
        amplitudes = np.arange(10, dtype=float)
        selected_f, selected_a = limit_spectrum_frequencies(
            frequencies, amplitudes, 0.2, 0.4)
        np.testing.assert_allclose(selected_f, [0.2, 0.3, 0.4])
        np.testing.assert_allclose(selected_a, [2, 3, 4])
        for kwargs, message in (
                ({"minimum": -1}, "nonnegative"),
                ({"minimum": float("nan")}, "finite"),
                ({"minimum": 0.4, "maximum": 0.2}, "exceed"),
                ({"minimum": 1.5}, "no FFT bins")):
            with self.subTest(kwargs=kwargs):
                with self.assertRaisesRegex(ValueError, message):
                    limit_spectrum_frequencies(frequencies, amplitudes,
                                               **kwargs)

    def test_db_scaling_floor_and_validation(self):
        values = np.array([0.0, 0.001, 0.1, 1.0])
        original = values.copy()
        result = spectrum_decibels(values)
        np.testing.assert_allclose(result, [-120.0, -60.0, -20.0, 0.0])
        np.testing.assert_array_equal(values, original)
        with self.assertRaisesRegex(ValueError, "reference peak"):
            spectrum_decibels(np.zeros(5))
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            spectrum_decibels(np.array([-1., 2.]))

    def test_no_mutation_of_input_arrays(self):
        times = np.arange(20, dtype=float)
        signal = np.sin(times)
        original = signal.copy()
        amplitude_spectrum(times, signal)
        np.testing.assert_array_equal(signal, original)


if __name__ == "__main__":
    unittest.main()
