#!/bin/bash

echo "Attaching to gridconnection_watcher.service logs..."
echo "Press Ctrl+C to exit."

# Run the journalctl command to follow logs
sudo journalctl -u gridconnection_watcher.service -f
