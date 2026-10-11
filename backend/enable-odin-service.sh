#!/bin/bash

# Create systemd service unit content
cat <<EOF > /tmp/odin-serve.service
[Unit]
Description=Odin Serve Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/odin serve
Restart=on-failure
User=$(whoami)
Environment=HOME=/home/$(whoami)

[Install]
WantedBy=multi-user.target
EOF

# Move the service file to systemd directory
sudo mv /tmp/odin-serve.service /etc/systemd/system/odin-serve.service

# Reload systemd daemon
sudo systemctl daemon-reload

# Enable the service to start at boot
sudo systemctl enable odin-serve.service

# Start the service immediately
sudo systemctl start odin-serve.service

# Check status
systemctl status odin-serve.service
