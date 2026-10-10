import httpx

from app.devices.base import CapabilityState, DeviceStatus, Operation
from app.devices.dahua.driver import DahuaDriver
from tests.fake_dahua import FakeDahua


def driver(fake: FakeDahua, password: str = "secret") -> DahuaDriver:
    return DahuaDriver("10.0.0.5", 80, "admin", password, transport=fake.transport())


def test_check_online_reads_identity_through_digest_auth():
    fake = FakeDahua()
    result = driver(fake).check()
    assert result.status == DeviceStatus.online
    assert result.identity.model == "DHI-ASI2212J-PW"
    assert result.identity.firmware == "1.000.0000000.1.R build 2023-03-15"
    assert result.identity.serial_no == "8F0A1B2C3D"
    assert fake.auth_headers[0] is None  # first request gets the Digest challenge
    assert fake.auth_headers[1].startswith("Digest ")


def test_wrong_password_is_auth_failed_and_error_hides_password():
    result = driver(FakeDahua(), password="WRONG-pass").check()
    assert result.status == DeviceStatus.auth_failed
    assert "WRONG-pass" not in (result.error or "")


def test_network_failures_are_offline():
    def boom(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    d = DahuaDriver("10.0.0.5", 80, "admin", "secret", transport=httpx.MockTransport(boom))
    result = d.check()
    assert result.status == DeviceStatus.offline
    assert result.error == "Connection timed out"


def test_unexpected_status_is_error():
    fake = FakeDahua()
    fake.routes[("magicBox.cgi", "getDeviceType")] = lambda r: httpx.Response(500)
    assert driver(fake).check().status == DeviceStatus.error


def test_model_falls_back_to_system_info():
    fake = FakeDahua()
    fake.routes[("magicBox.cgi", "getDeviceType")] = lambda r: httpx.Response(400)
    fake.routes[("magicBox.cgi", "getSystemInfo")] = lambda r: httpx.Response(
        200, text="deviceType=DHI-ASI1201E\r\nserialNumber=XYZ\r\n")
    result = driver(fake).check()
    assert result.status == DeviceStatus.online
    assert (result.identity.model, result.identity.serial_no) == ("DHI-ASI1201E", "XYZ")


def test_probe_capabilities_only_uses_read_only_actions():
    fake = FakeDahua()
    caps = driver(fake).probe_capabilities()
    assert caps[Operation.history_read].state == CapabilityState.verified
    assert caps[Operation.users_read].state == CapabilityState.verified
    assert caps[Operation.cards_read_legacy].state == CapabilityState.unsupported  # fake answers 400
    assert caps[Operation.users_write].state == CapabilityState.unverified
    actions = {r.url.params.get("action") for r in fake.requests}
    assert actions <= {"getDeviceType", "find", "startFind", "stopFind"}
    # every search cursor that was opened is closed again
    authed = [r.url.params.get("action") for r, h in zip(fake.requests, fake.auth_headers, strict=True) if h]
    assert authed.count("startFind") == authed.count("stopFind") == 2


def test_history_probe_uses_unix_integer_times():
    fake = FakeDahua()
    driver(fake).probe_capabilities()
    rec = next(r for r in fake.requests if r.url.params.get("name") == "AccessControlCardRec")
    assert rec.url.params["StartTime"].isdigit() and rec.url.params["EndTime"].isdigit()


def test_probe_marks_missing_user_api_unsupported():
    caps = driver(FakeDahua(supports_user_api=False)).probe_capabilities()
    assert caps[Operation.users_read].state == CapabilityState.unsupported
    assert caps[Operation.cards_read].state == CapabilityState.unsupported
