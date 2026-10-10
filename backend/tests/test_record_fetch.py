import random
from datetime import UTC, datetime

import pytest

from app.devices.dahua.records import (
    FetchStats,
    RecordFetchError,
    TruncationError,
    fetch_window,
    normalize_record,
)

T0 = 1_780_000_000


def make_device(times: list[int], *, end_exclusive=False, newest_first=False, cap=1024):
    """Simulated recordFinder: filter by CreateTime, sort, truncate to min(count, cap)."""
    records = [{"RecNo": str(i + 1), "CreateTime": str(t), "CardName": f"P{i}"} for i, t in enumerate(sorted(times))]
    calls = []

    def query(start, end, count):
        calls.append((start, end))
        hit = [r for r in records if start <= int(r["CreateTime"]) < end + (0 if end_exclusive else 1)]
        hit.sort(key=lambda r: int(r["CreateTime"]), reverse=newest_first)
        hit = hit[:min(count, cap)]
        lines = [f"found={len(hit)}"]
        for i, r in enumerate(hit):
            lines += [f"records[{i}].{k}={v}" for k, v in r.items()]
        return "\r\n".join(lines) + "\r\n"

    return records, query, calls


def test_small_window_single_query():
    records, query, calls = make_device([T0 + i * 60 for i in range(10)])
    out = fetch_window(query, T0, T0 + 3600)
    assert [r["RecNo"] for r in out] == [r["RecNo"] for r in records]
    assert len(calls) == 1


def test_window_over_cap_is_split_and_nothing_is_lost():
    times = [T0 + i * 7 for i in range(5000)]  # 5000 records over ~10 hours
    records, query, calls = make_device(times)
    stats = FetchStats()
    out = fetch_window(query, T0, T0 + 86400, stats=stats)
    assert len(out) == 5000
    assert {r["RecNo"] for r in out} == {r["RecNo"] for r in records}
    assert stats.splits > 0 and stats.queries == len(calls)


@pytest.mark.parametrize("end_exclusive", [False, True])
@pytest.mark.parametrize("newest_first", [False, True])
def test_boundary_semantics_and_order_do_not_lose_records(end_exclusive, newest_first):
    # Records exactly on likely split points.
    times = [T0 + 43200] * 300 + [T0 + 43201] * 300 + [T0 + i for i in range(0, 86400, 60)]
    records, query, _ = make_device(times, end_exclusive=end_exclusive, newest_first=newest_first)
    out = fetch_window(query, T0, T0 + 86400)
    assert len(out) == len(records)


def test_randomized_distributions():
    rng = random.Random(1234)
    for _ in range(25):
        n = rng.randint(0, 6000)
        burst_at = T0 + rng.randint(0, 86400)
        times = [rng.choice([burst_at, T0 + rng.randint(0, 86400)]) for _ in range(n)]
        # keep each second under the cap so it is fetchable
        times = [t for t in times if times.count(t) < 1000] if n < 1500 else \
            [T0 + rng.randint(0, 86400) for _ in range(n)]
        records, query, _ = make_device(times, end_exclusive=rng.random() < 0.5)
        out = fetch_window(query, T0, T0 + 86400)
        assert len(out) == len(records)


def test_more_than_cap_in_one_second_raises_instead_of_dropping():
    _, query, _ = make_device([T0 + 5] * 1500)
    with pytest.raises(TruncationError):
        fetch_window(query, T0, T0 + 10)


def test_small_cap_still_complete():
    records, query, _ = make_device([T0 + i for i in range(200)], cap=10)
    assert len(fetch_window(query, T0, T0 + 1000, cap=10)) == 200


def test_unexpected_response_raises():
    with pytest.raises(RecordFetchError):
        fetch_window(lambda s, e, c: "Error\r\nBad Request!\r\n", T0, T0 + 10)


def test_found_mismatch_is_reported_not_hidden():
    stats = FetchStats()
    fetch_window(lambda s, e, c: "found=3\r\nrecords[0].RecNo=1\r\nrecords[0].CreateTime=1\r\n", T0, T0 + 10,
                 stats=stats)
    assert stats.warnings and "found=3" in stats.warnings[0]


def test_record_without_recno_is_reported():
    stats = FetchStats()
    out = fetch_window(lambda s, e, c: "found=1\r\nrecords[0].CreateTime=5\r\n", T0, T0 + 10, stats=stats)
    assert out == [] and "RecNo" in stats.warnings[0]


def test_normalize_record():
    raw = {"RecNo": "77", "CreateTime": "1783485269", "UserID": "1001", "CardName": "John Smith",
           "CardNo": "AB12CD34", "Type": "Entry", "Method": "1", "Status": "1", "Door": "0",
           "ReaderID": "1", "ErrorCode": "0", "Password": "", "URL": ""}
    n = normalize_record(raw)
    assert n["rec_no"] == 77
    assert n["event_time"] == datetime(2026, 7, 8, 4, 34, 29, tzinfo=UTC)
    assert (n["device_user_id"], n["card_name"], n["card_no"], n["type"]) == ("1001", "John Smith", "AB12CD34", "Entry")
    assert (n["method"], n["status"], n["door"], n["reader_id"], n["error_code"]) == (1, 1, 0, "1", 0)
    assert n["raw_payload"]["CardName"] == "John Smith"


def test_normalize_record_redacts_pins():
    n = normalize_record({"RecNo": "1", "CreateTime": "1", "Password": "4321", "CardPassword": ""})
    assert n["raw_payload"]["Password"] == "[redacted]"
    assert n["raw_payload"]["CardPassword"] == ""


def test_normalize_record_tolerates_missing_and_bad_fields():
    n = normalize_record({"RecNo": "5", "CreateTime": "x", "Status": ""})
    assert n["event_time"] is None and n["status"] is None and n["card_name"] is None
