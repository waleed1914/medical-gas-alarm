# Medical Gas Web Dashboard

## Start it

1. Stop `Medical_Gas_Dashboard.py` and `panel_receiver_test.py`. A panel accepts only one dashboard connection.
2. Double-click `Start_Web_Dashboard.bat`.
3. On the server PC, open `http://127.0.0.1:8080`.
4. Sign in with username `admin` and password `medical12345`.

The web server connects directly to all panel IP addresses from `dashboard_config.json`. Only connected panels appear. Panel names also come from that file.

## Open it from the local network

Use `http://PC_LAN_IP:8080` from another device. For example, if the PC is `192.168.10.1`, open `http://192.168.10.1:8080`.

Allow inbound TCP port 8080 in Windows Defender Firewall if Windows asks. Keep the PC awake and keep the command window open.

## Open it from the Internet

1. Give the PC a fixed LAN address or DHCP reservation.
2. In the Internet router, forward an external TCP port to the PC's LAN address, port 8080.
3. Open `http://PUBLIC_IP:EXTERNAL_PORT` from outside the building network.

This will work only if the Internet provider gives the router a public IPv4 address. If it uses CGNAT, router port forwarding will not work without requesting a public IP or using a tunnel/VPN service.

The remote dashboard is read-only: it provides no mute, test, calibration, or naming commands. Its only POST actions are login and logout.

## Important

Plain port forwarding uses HTTP, so the login and pressure data are not encrypted while travelling over the Internet. Change the default password before deployment and preferably add HTTPS through a reverse proxy.
