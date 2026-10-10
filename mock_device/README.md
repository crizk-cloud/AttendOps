# mock_device (development only)

`fake_dahua_server.py` starts **fake** Dahua devices on localhost so you can try AttendOps without hardware.
The backend never imports this, and nothing tested against it counts as verified on real devices.

```bash
python3 mock_device/fake_dahua_server.py --count 3 --base-port 18081 --password demo-pass
```

Then register `127.0.0.1` on ports 18081–18083 (username `admin`, password `demo-pass`). The fake model shows as
`DHI-ASI2212J-PW (FAKE)`. Run the backend directly (not in Docker) when using the fake, so `127.0.0.1` reaches it.
