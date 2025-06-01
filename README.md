# Smart Medication Management System 💊

A comprehensive medication management solution combining hardware and software to help users manage their medications effectively and safely.

## Features ✨
- **Real-time Weight Monitoring** ⚖️: Tracks medication weight in real-time using Arduino and the HX711 weight sensor.
- **Medication Inventory Management** 📦:
  - Track multiple medications simultaneously.
  - Automatic pill counting based on weight.
  - Support for different pill weights per medication.
- **Smart Dispensing Sessions** 🚀:
  - Controlled medication dispensing.
  - Secure compartment locking/unlocking.
  - Detailed consumption tracking.
- **Dual Operation Modes** 🔄:
  - Real mode for actual medication management.
  - Simulation mode for testing and setup.
- **Web Interface** 🌐:
  - Real-time status monitoring.
  - Easy medication setup and configuration.
  - Inventory management dashboard.

## Hardware Requirements 🛠️
- Arduino board.
- HX711 weight sensor.
- Medication compartments with locking mechanism.
- Serial connection capability.

## Software Requirements 💻
- Python 3.x.
- Flask.
- PySerial.
- Web browser.

## Dependencies & Libraries 📚

### Python Libraries 📦
- **Flask**: Lightweight web framework powering the web interface.
- **PySerial**: Provides serial communication between Python and Arduino.
- **requests**: HTTP client for sending medication data to cloud servers.
- **pyngrok**: Exposes the local Flask server via ngrok for remote access.

### Arduino Libraries 📚
- **SoftwareWire**: Software-based I2C communication.
- **MPU6050**: Interface for the MPU-6050 accelerometer/gyroscope sensor.
- **LiquidCrystal_I2C**: Control I2C-connected LCD displays.
- **LiquidCrystal**: Control standard parallel LCD displays.
- **I2Cdev**: Lower-level I2C device interface library.
- **Grove_Ultrasonic_Ranger**: Interface for Grove ultrasonic distance sensor.
- **DFRobot_HX711_I2C**: Wrapper for the HX711 weight sensor module.
- **mp3-main**: Controls MP3 playback modules.

## Installation 📥
1. Set up Python Environment:
   - Install Python 3.6 or higher.
   - Create and activate a virtual environment:
     ```bash
     python -m venv venv
     # Windows PowerShell
     venv\Scripts\Activate.ps1
     # Unix or Git Bash
     source venv/bin/activate
     ```
2. Install Python dependencies:
   ```bash
   pip install flask pyserial requests pyngrok
   ```
3. Install Arduino libraries:
   - Copy the entire `libraries/` folder into your Arduino IDE libraries directory (e.g., `C:\Users\<YourUser>\Documents\Arduino\libraries\`).
   - Or open the Arduino IDE and go to Sketch > Include Library > Add .ZIP Library, then select each library folder from `libraries/`.

## Usage 🚀

### Local Usage
1. Connect your Arduino to the computer via serial port.
2. Ensure the Python virtual environment (if used) is activated.
3. Start the Flask server:
   ```bash
   python app.py
   ```
4. Open your web browser and navigate to `http://localhost:5000`.
5. On the web interface, click the "Simulation Mode" or "Real Mode" button at the top to switch operation modes.
6. Follow on-screen instructions to configure medications and sessions.

### Remote Access via ngrok
1. Make sure ngrok is installed and authenticated.
2. Run an ngrok tunnel:
   ```bash
   ngrok http 5000
   ```
3. Share the generated public URL with authorized users for remote monitoring.

## Cloud Synchronization & Remote Access ☁️
To sync medication records to your cloud server:
1. Set the environment variable `CLOUD_SERVER_URL`:
   ```bash
   export CLOUD_SERVER_URL="https://your-cloud-server.com/api/consumption"
   ```
2. The application will automatically send consumption records to the specified endpoint after each session.

## Persisting ngrok Authentication Token 🔑
To avoid entering the token every time:
1. **Set environment variable (Windows PowerShell)**:
   ```powershell
   [Environment]::SetEnvironmentVariable("NGROK_AUTH_TOKEN", "your_token_here", "User")
   ```
2. **Set default token in code**:
   Open `app.py` and replace `YOUR_NGROK_AUTH_TOKEN`:
   ```python
   NGROK_AUTH_TOKEN = os.environ.get("NGROK_AUTH_TOKEN", "your_token_here")
   ```

## Safety Features 🔒
- Secure compartment locking mechanism.
- Real-time weight verification.
- Automatic pill counting.
- Session-based medication dispensing.

## View Medication History 📜
After running the application, view real-time medication history at:
```
http://<your_remote_domain>/history
```

## Contributing 🤝
Contributions are welcome! Please submit a pull request or open an issue.

## License 📄
[Insert your license here]

## Support 📞
For support, please [insert contact information or support channels]. 