# Ecowitt E-Ink Display

Raspberry Pi weather dashboard for an Ecowitt GW2000 and Waveshare 2.13 inch e-Paper HAT V2.

## Run On Startup

Clone this repo on the Pi:

```bash
cd /home/tflowers
git clone https://github.com/timistim/ecowitt-eink-display.git
```

Install Python dependencies if needed:

```bash
sudo apt update
sudo apt install -y python3-pil python3-requests
```

Install and start the systemd service:

```bash
sudo cp /home/tflowers/ecowitt-eink-display/systemd/ecowitt-eink-display.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ecowitt-eink-display.service
sudo systemctl start ecowitt-eink-display.service
```

Check status and logs:

```bash
systemctl status ecowitt-eink-display.service
journalctl -u ecowitt-eink-display.service -f
```

Restart after pulling code changes:

```bash
cd /home/tflowers/ecowitt-eink-display
git pull
sudo systemctl restart ecowitt-eink-display.service
```
