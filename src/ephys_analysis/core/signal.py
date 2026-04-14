import numpy as np


def time_to_index(t_sec: float, sample_rate: float) -> int:
    return int(round(t_sec * sample_rate))


def windowed_mean(data: np.ndarray, t_start: float, t_end: float, sample_rate: float) -> float:
    i0 = time_to_index(t_start, sample_rate)
    i1 = time_to_index(t_end, sample_rate)
    return float(np.mean(data[i0:i1]))


def windowed_peak(data: np.ndarray, t_start: float, t_end: float, sample_rate: float) -> float:
    i0 = time_to_index(t_start, sample_rate)
    i1 = time_to_index(t_end, sample_rate)
    return float(np.max(data[i0:i1]))


def windowed_antipeak(data: np.ndarray, t_start: float, t_end: float, sample_rate: float) -> float:
    i0 = time_to_index(t_start, sample_rate)
    i1 = time_to_index(t_end, sample_rate)
    return float(np.min(data[i0:i1]))
