# AWS deployment

The cloud package is ready, but an AWS EC2 instance and a domain name are still required for a secure public deployment.

## Architecture

The Windows PC connects to all Pico panels and uploads one read-only snapshot each second to AWS over HTTPS. AWS never connects inward to the hospital network. Browsers connect only to AWS.

## EC2

Create an Ubuntu LTS EC2 instance. A small instance is enough for this dashboard. Give it an Elastic IP so the address does not change. Its security group should allow:

- TCP 22 from your own administration IP only.
- TCP 80 from anywhere.
- TCP 443 from anywhere.

Do not expose TCP 8000 or 5050.

Point a domain or subdomain, such as `gas.example.com`, to the Elastic IP.

## Upload these files to `/tmp/medical-gas`

- `Medical_Gas_Cloud_Server.py`
- `cloud_config.json`
- `requirements-cloud.txt`
- `templates/`
- `static/`
- `aws/`

Then connect by SSH and run:

```bash
sudo apt update
sudo apt install -y python3-venv nginx certbot python3-certbot-nginx
sudo useradd --system --home /opt/medical-gas --shell /usr/sbin/nologin medicalgas
sudo mkdir -p /opt/medical-gas
sudo cp -r /tmp/medical-gas/Medical_Gas_Cloud_Server.py /tmp/medical-gas/cloud_config.json /tmp/medical-gas/requirements-cloud.txt /tmp/medical-gas/templates /tmp/medical-gas/static /opt/medical-gas/
sudo python3 -m venv /opt/medical-gas/venv
sudo /opt/medical-gas/venv/bin/pip install -r /opt/medical-gas/requirements-cloud.txt
sudo chown -R medicalgas:medicalgas /opt/medical-gas
sudo cp /tmp/medical-gas/aws/medical-gas.service /etc/systemd/system/
sudo sed 's/YOUR_DOMAIN/gas.example.com/g' /tmp/medical-gas/aws/nginx-medical-gas.conf | sudo tee /etc/nginx/sites-available/medical-gas >/dev/null
sudo ln -s /etc/nginx/sites-available/medical-gas /etc/nginx/sites-enabled/medical-gas
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now medical-gas nginx
sudo certbot --nginx -d gas.example.com
```

Replace `gas.example.com` with the real domain in both commands.

## Connect the Windows collector

In `web_config.json`:

1. Set `cloud.enabled` to `true`.
2. Replace `https://YOUR_DOMAIN/api/ingest` with the real HTTPS domain.
3. Keep the token exactly matched with `cloud_config.json` on AWS.
4. Restart `Medical_Gas_Web_Server.py`.

The public dashboard will then be `https://YOUR_DOMAIN` with username `admin` and the selected password. The local dashboard continues to work at `http://127.0.0.1:8080`.

## Secrets

`cloud_config.json` and `web_config.json` contain the private ingest token. Do not publish or email these files. They are excluded from Git; use the committed `.example.json` templates when setting up another machine. Change the login password before handing the system to the client.
