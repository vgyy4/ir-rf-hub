"""signal_shapes.py in isolation -- no device/session/HTTP involved, just
the clustering and NEC-detection logic itself.
"""

from __future__ import annotations

from ir_rf_hub.esphome.signal_shapes import cluster_captures, detect_multi_shape_protocol

NEC_LEADER = [9000, -4500] + [560, -560, 560, -1690] * 16  # 66 edges, a plausible 32-bit-ish frame
NEC_REPEAT = [9000, -2250, 560]


def test_identical_repeats_collapse_into_one_cluster():
    captures = [[100, -100, 200], [101, -99, 201], [99, -101, 199]]
    clusters = cluster_captures(captures)
    assert len(clusters) == 1
    assert clusters[0].occurrences == 3
    assert clusters[0].edge_count == 3


def test_a_real_frame_and_a_short_garbled_echo_form_separate_clusters():
    full_frame = [4500, -4500] + [560, -560] * 32
    garbled_echo = [278, -997, 276, -398, 278, -699, 275]
    clusters = cluster_captures([full_frame, garbled_echo])
    assert len(clusters) == 2
    by_edges = sorted(clusters, key=lambda c: c.edge_count)
    assert by_edges[0].timings == garbled_echo
    assert by_edges[1].timings == full_frame


def test_different_edge_count_never_merges_even_if_first_edges_match():
    clusters = cluster_captures([[100, -100], [100, -100, 200]])
    assert len(clusters) == 2


def test_sign_mismatch_never_merges_even_if_magnitude_matches():
    # a mark and a space of the same duration are not the same edge
    clusters = cluster_captures([[100, -100], [100, 100]])
    assert len(clusters) == 2


def test_occurrences_and_first_seen_index_track_arrival_order():
    captures = [[500, -500], [9000, -2250, 560], [501, -499]]
    clusters = cluster_captures(captures)
    assert len(clusters) == 2
    assert clusters[0].first_seen_index == 0
    assert clusters[0].occurrences == 2
    assert clusters[1].first_seen_index == 1
    assert clusters[1].occurrences == 1


def test_detects_nec_leader_and_repeat_regardless_of_arrival_order():
    clusters = cluster_captures([NEC_LEADER, NEC_REPEAT, NEC_REPEAT])
    detected = detect_multi_shape_protocol(clusters)
    assert detected is not None
    assert detected.name == "nec_leader_repeat"
    assert detected.leader_timings == NEC_LEADER
    assert detected.repeat_timings == NEC_REPEAT

    # order shouldn't matter -- repeat captured first, leader second
    clusters_reordered = cluster_captures([NEC_REPEAT, NEC_LEADER])
    detected_reordered = detect_multi_shape_protocol(clusters_reordered)
    assert detected_reordered is not None
    assert detected_reordered.leader_timings == NEC_LEADER
    assert detected_reordered.repeat_timings == NEC_REPEAT


def test_two_edge_repeat_code_without_trailing_mark_still_detected():
    # some receivers may not capture the final trailing mark
    short_repeat = [9000, -2250]
    clusters = cluster_captures([NEC_LEADER, short_repeat])
    detected = detect_multi_shape_protocol(clusters)
    assert detected is not None
    assert detected.repeat_timings == short_repeat


def test_no_detection_when_only_one_shape_present():
    clusters = cluster_captures([NEC_LEADER, NEC_LEADER])
    assert detect_multi_shape_protocol(clusters) is None


def test_no_detection_for_two_unrelated_non_nec_shapes():
    # e.g. the actual Netflix bug: a real full frame + genuine noise --
    # neither NEC-shaped, so nothing should be auto-saved as a protocol
    full_frame = [4500, -4500] + [560, -560] * 32
    garbled_echo = [278, -997, 276, -398, 278, -699, 275]
    clusters = cluster_captures([full_frame, garbled_echo])
    assert detect_multi_shape_protocol(clusters) is None


def test_no_detection_when_leader_shaped_but_too_short():
    # right header, but not enough edges to plausibly be a real 32-bit frame
    almost_leader = [9000, -4500, 560, -560]
    clusters = cluster_captures([almost_leader, NEC_REPEAT])
    assert detect_multi_shape_protocol(clusters) is None
