from app.devices.dahua.driver import parse_firmware
from app.devices.dahua.parsing import parse_event_line, parse_indexed, parse_kv

# Shape taken from the verified device format (and dahua_attendance_logger.py's docstring).
RECORDS = """found=2\r
records[0].RecNo=101\r
records[0].CreateTime=1783485269\r
records[0].CardName=John Smith\r
records[0].Type=Entry\r
records[1].RecNo=102\r
records[1].CreateTime=1783485300\r
records[1].CardName=A=B Name\r
\r
"""


def test_parse_kv_splits_on_first_equals_and_strips_crlf():
    assert parse_kv("type=DHI-ASI2212J-PW\r\nversion=1.0,build:2023\r\nnoequals\r\n") == {
        "type": "DHI-ASI2212J-PW", "version": "1.0,build:2023"}


def test_parse_indexed_records():
    top, recs = parse_indexed(RECORDS)
    assert top == {"found": "2"}
    assert [r["RecNo"] for r in recs] == ["101", "102"]
    assert recs[0]["CardName"] == "John Smith"
    assert recs[1]["CardName"] == "A=B Name"


def test_parse_indexed_orders_by_index_not_by_line():
    _, recs = parse_indexed("records[1].RecNo=2\nrecords[0].RecNo=1\nrecords[10].RecNo=11\n")
    assert [r["RecNo"] for r in recs] == ["1", "2", "11"]


def test_parse_indexed_empty_result():
    assert parse_indexed("found=0\r\n") == ({"found": "0"}, [])


def test_parse_event_line():
    ev = parse_event_line('Code=AccessControlEvent;action=Pulse;index=0;data={"CardNo":"AB12","Status":1}')
    assert ev == {"Code": "AccessControlEvent", "action": "Pulse", "index": "0",
                  "data": {"CardNo": "AB12", "Status": 1}}
    assert parse_event_line("Heartbeat") is None
    assert parse_event_line("--myboundary") is None
    assert parse_event_line("Code=X;action=Pulse;index=0;data={broken")["data_raw"] == "{broken"


def test_parse_firmware():
    raw = "version=1.000.0000000.1.R,build:2023-03-15\r\n"
    assert parse_firmware(raw) == "1.000.0000000.1.R build 2023-03-15"
    assert parse_firmware("nothing\r\n") is None
