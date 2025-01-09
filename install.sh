#!/bin/bash

echo "Starting installation of gridconnection watcher..."

# Detect the script directory
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
echo "Detected script directory: $SCRIPT_DIR"

# Detect the Python executable
PYTHON_EXEC=$(which python3)
if [ -z "$PYTHON_EXEC" ]; then
    echo "Error: Python3 is not installed or not found in PATH."
    exit 1
fi
echo "Using Python executable: $PYTHON_EXEC"

# Detect the current user
CURRENT_USER=$(whoami)
echo "Detected current user: $CURRENT_USER"

# Ensure the Python script is executable
echo "Checking if gridconnection_watcher.py exists and is executable..."
if [ -f "$SCRIPT_DIR/gridconnection_watcher.py" ]; then
    chmod +x "$SCRIPT_DIR/gridconnection_watcher.py"
    echo "Marked gridconnection_watcher.py as executable."
else
    echo "Error: gridconnection_watcher.py not found in $SCRIPT_DIR."
    exit 1
fi

# Create the service file
SERVICE_FILE_PATH="/lib/systemd/system/gridconnection_watcher.service"
echo "Creating systemd service file at $SERVICE_FILE_PATH..."
cat <<EOL > $SERVICE_FILE_PATH
[Unit]
Description=gridconnection watcher
After=network.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart=$PYTHON_EXEC $SCRIPT_DIR/gridconnection_watcher.py
KillSignal=SIGINT
Restart=on-failure
User=$CURRENT_USER

[Install]
WantedBy=multi-user.target
EOL

if [ $? -eq 0 ]; then
    echo "Service file created successfully."
else
    echo "Error: Failed to create service file."
    exit 1
fi

# Set proper permissions for the service file
echo "Setting permissions for the service file..."
chmod 644 $SERVICE_FILE_PATH
if [ $? -eq 0 ]; then
    echo "Permissions set successfully."
else
    echo "Error: Failed to set permissions for service file."
    exit 1
fi

# Enable the systemd service
echo "Enabling the systemd service..."
sudo systemctl enable gridconnection_watcher.service
if [ $? -eq 0 ]; then
    echo "Service enabled successfully."
else
    echo "Error: Failed to enable the service."
    exit 1
fi

# Start the systemd service
echo "Starting the systemd service..."
sudo systemctl start gridconnection_watcher.service
if [ $? -eq 0 ]; then
    echo "Service started successfully."
else
    echo "Error: Failed to start the service."
    exit 1
fi

echo "Installation finished successfully!"
