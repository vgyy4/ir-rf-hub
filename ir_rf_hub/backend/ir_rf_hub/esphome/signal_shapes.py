"""Turns the raw per-event captures from one recording session into either
a single canonical signal, an auto-detected multi-shape protocol (leader +
repeat frame), or a set of candidate shapes for the user to choose from --
see api/rest/recording.py's stop_recording().

Why this exists: a single button press can trigger several distinct
receive events -- a remote genuinely repeating its own signal, or the
receiver's own AGC producing a short noise burst right after handling a
strong real signal (confirmed against a real recording: a correct 68-edge
Samsung frame followed by a garbled 8-edge blip). Naively keeping
"whichever capture arrived last" saves noise as the command. Clustering by
shape similarity, then picking (or asking about) the most complete
cluster, is robust to that regardless of arrival order -- and lets a
*genuine* second shape (like a real NEC repeat code) be recognized instead
of discarded.
"""

from __future__ import annotations

from dataclasses import dataclass

# Two captures are the "same shape" if they have the same edge count and
# every corresponding edge is within this fraction of the other -- loose
# enough to absorb normal measurement jitter between repeated presses of a
# real remote, tight enough that a genuinely different signal (or a short
# noise burst) won't accidentally merge with a real frame.
_SIMILARITY_TOLERANCE = 0.25


def _edges_similar(a: int, b: int, tolerance: float) -> bool:
    if (a < 0) != (b < 0):
        return False
    return abs(abs(a) - abs(b)) <= tolerance * max(abs(a), abs(b), 1)


def _shapes_similar(a: list[int], b: list[int], tolerance: float = _SIMILARITY_TOLERANCE) -> bool:
    if len(a) != len(b):
        return False
    return all(_edges_similar(x, y, tolerance) for x, y in zip(a, b))


@dataclass
class ShapeCluster:
    timings: list[int]
    occurrences: int
    first_seen_index: int

    @property
    def edge_count(self) -> int:
        return len(self.timings)


def cluster_captures(captures: list[list[int]]) -> list[ShapeCluster]:
    """Groups captures into distinct shapes, preserving first-seen order.
    Within a cluster, the representative timings are whichever capture was
    seen first -- members are similar by definition, so any would do.
    """
    clusters: list[ShapeCluster] = []
    for index, timings in enumerate(captures):
        match = next((c for c in clusters if _shapes_similar(c.timings, timings)), None)
        if match is not None:
            match.occurrences += 1
        else:
            clusters.append(ShapeCluster(timings=timings, occurrences=1, first_seen_index=index))
    return clusters


@dataclass
class DetectedProtocol:
    name: str
    leader_timings: list[int]
    repeat_timings: list[int]


# NEC-family timings, generously toleranced for real-world encoder
# variance. Per https://www.sbprojects.net/knowledge/ir/nec.php: the full
# 32-bit leader frame is a 9ms mark + 4.5ms space + the bit stream (dozens
# of edges); while held, the remote switches to a much shorter, distinctly
# different "repeat code" -- 9ms mark + 2.25ms space + a single trailing
# ~562.5us mark. That's the only widely-documented consumer IR/RF protocol
# where a single press legitimately produces two *structurally different*
# frame shapes rather than repeating one shape verbatim (which is already
# handled correctly with no detection needed: clustering collapses those
# into a single shape on its own).
_NEC_LEADER_MARK_RANGE = (7500, 10500)
_NEC_LEADER_SPACE_RANGE = (3800, 5200)
_NEC_REPEAT_SPACE_RANGE = (1900, 2700)
_NEC_LEADER_MIN_EDGES = 20


def _looks_like_nec_leader(timings: list[int]) -> bool:
    if len(timings) < _NEC_LEADER_MIN_EDGES:
        return False
    mark, space = timings[0], timings[1]
    return _NEC_LEADER_MARK_RANGE[0] <= mark <= _NEC_LEADER_MARK_RANGE[1] and (
        _NEC_LEADER_SPACE_RANGE[0] <= -space <= _NEC_LEADER_SPACE_RANGE[1]
    )


def _looks_like_nec_repeat(timings: list[int]) -> bool:
    if len(timings) not in (2, 3):
        return False
    mark, space = timings[0], timings[1]
    return _NEC_LEADER_MARK_RANGE[0] <= mark <= _NEC_LEADER_MARK_RANGE[1] and (
        _NEC_REPEAT_SPACE_RANGE[0] <= -space <= _NEC_REPEAT_SPACE_RANGE[1]
    )


def detect_multi_shape_protocol(clusters: list[ShapeCluster]) -> DetectedProtocol | None:
    leader = next((c for c in clusters if _looks_like_nec_leader(c.timings)), None)
    repeat = next((c for c in clusters if _looks_like_nec_repeat(c.timings)), None)
    if leader is None or repeat is None:
        return None
    return DetectedProtocol(name="nec_leader_repeat", leader_timings=leader.timings, repeat_timings=repeat.timings)
