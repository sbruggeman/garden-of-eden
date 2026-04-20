import threading
import statistics
import logging
from time import sleep

logger = logging.getLogger(__name__)

RING_BUFFER_SIZE = 20
# Readings outside this range are discarded as sensor errors.
# A full tank reads ~10-12 cm; near-empty reads ~23 cm on Gardyn 4.0.
# Below 3 cm = sensor error or overflow; above 25 cm = out of range / empty.
VALID_MIN_CM = 3.0
VALID_MAX_CM = 25.0
COUNT_FOR_VALUE = 6
SAMPLE_INTERVAL_SECONDS = 10
STABLE_VALUE_THRESHOLD_CM = 1.0
REALTIME_CHANGE_THRESHOLD_CM = 2.0


class WaterLevelSampler:
    """
    Maintains a rolling ring buffer of distance readings and publishes smoothed
    water level values. Readings outside the valid sensor range are discarded.
    Publishes the median of the last 6 valid readings to suppress sensor noise.
    """

    def __init__(self, sensor_fn, on_publish,
                 ring_buffer_size=RING_BUFFER_SIZE,
                 valid_min_cm=VALID_MIN_CM,
                 valid_max_cm=VALID_MAX_CM,
                 count_for_value=COUNT_FOR_VALUE,
                 sample_interval=SAMPLE_INTERVAL_SECONDS,
                 stable_threshold=STABLE_VALUE_THRESHOLD_CM,
                 realtime_threshold=REALTIME_CHANGE_THRESHOLD_CM):
        self._sensor_fn = sensor_fn
        self._on_publish = on_publish
        self._ring_buffer_size = ring_buffer_size
        self._valid_min = valid_min_cm
        self._valid_max = valid_max_cm
        self._count_for_value = count_for_value
        self._sample_interval = sample_interval
        self._stable_threshold = stable_threshold
        self._realtime_threshold = realtime_threshold

        self._ring_buffer = []
        self._stable_value = None
        self._last_value_sent = None
        self._lock = threading.Lock()

    def add_reading(self, distance_cm):
        if distance_cm is None:
            return
        if not (self._valid_min < distance_cm < self._valid_max):
            return

        publish_value = None
        with self._lock:
            self._ring_buffer.append(distance_cm)
            if len(self._ring_buffer) > self._ring_buffer_size:
                self._ring_buffer = self._ring_buffer[-self._ring_buffer_size:]
            publish_value = self._evaluate()

        if publish_value is not None:
            self._on_publish(publish_value)

    def _evaluate(self):
        """Called under lock. Returns a value to publish, or None."""
        if len(self._ring_buffer) < self._count_for_value:
            return None

        current_median = statistics.median(self._ring_buffer[-self._count_for_value:])

        if self._stable_value is None:
            self._stable_value = current_median
            self._last_value_sent = current_median
            return current_median

        if abs(current_median - self._stable_value) > self._stable_threshold:
            self._stable_value = current_median

        if self._last_value_sent is not None:
            if abs(current_median - self._last_value_sent) > self._realtime_threshold:
                self._last_value_sent = current_median
                return current_median

        return None

    def get_current_value(self):
        with self._lock:
            return self._stable_value

    def run(self):
        while True:
            try:
                distance = self._sensor_fn()
                self.add_reading(distance)
            except Exception as e:
                logger.error(f"WaterLevelSampler sensor error: {e}")
            sleep(self._sample_interval)

    def start(self):
        t = threading.Thread(target=self.run, daemon=True)
        t.start()
        return t
