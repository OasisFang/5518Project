# Smart Medication Management System

A comprehensive medication management system that combines hardware and software solutions to help users manage their medications effectively and safely.

## Features

- **Real-time Weight Monitoring**: Tracks medication weight in real-time using Arduino and HX711 weight sensor
- **Medication Inventory Management**: 
  - Track multiple medications simultaneously
  - Automatic pill counting based on weight
  - Support for different pill weights per medication
- **Smart Medication Sessions**:
  - Controlled medication dispensing
  - Secure compartment locking/unlocking
  - Consumption tracking
- **Dual Operation Modes**:
  - Real mode for actual medication management
  - Simulation mode for testing and setup
- **Web Interface**:
  - Real-time status monitoring
  - Easy medication setup and configuration
  - Inventory management dashboard

## Hardware Requirements

- Arduino board
- HX711 weight sensor
- Medication compartments with locking mechanism
- Serial connection capability

## Software Requirements

- Python 3.x
- Flask
- PySerial
- Web browser

## Installation

1. Clone the repository:
```bash
git clone [repository-url]
cd [repository-name]
```

2. Install required Python packages:
```bash
pip install flask pyserial
```

3. Configure the serial port:
   - Open `app.py`
   - Modify `SERIAL_PORT` and `BAUD_RATE` according to your setup

## Usage

1. Start the application:
```bash
python app.py
```

2. Access the web interface:
   - Open your web browser
   - Navigate to `http://localhost:5000`

3. Initial Setup:
   - Configure your medications in the medication setup page
   - Set up weight per pill (WPP) for each medication
   - Test the system in simulation mode before using with real medications

4. Regular Operation:
   - Monitor medication levels through the web interface
   - Use the medication session feature for controlled dispensing
   - Track consumption and inventory levels

## Cloud Synchronization and Remote Access

To sync medication records to your cloud server:

1. Set the environment variable `CLOUD_SERVER_URL` to your server's API endpoint, e.g.:
   ```bash
   export CLOUD_SERVER_URL="https://your-cloud-server.com/api/consumption"
   ```
2. Install the HTTP client:
   ```bash
   pip install requests
   ```
3. The application will automatically send medication consumption records to the specified `CLOUD_SERVER_URL` after each session.

To expose your local server via ngrok for remote access:

1. Download and install ngrok from https://ngrok.com/.
2. Authenticate your ngrok client:
   ```bash
   ngrok authtoken YOUR_NGROK_AUTH_TOKEN
   ```
3. Run the Flask application:
   ```bash
   python app.py
   ```
4. In a separate terminal, start ngrok tunnel:
   ```bash
   ngrok http 5000
   ```
5. Share the generated public URL (e.g., `https://abc123.ngrok.io`) with your doctors so they can access the web interface remotely.

### 保存 ngrok 认证令牌

为了避免每次手动输入 token，您可以永久保存令牌：

1. **设置环境变量（Windows PowerShell）**：
   ```powershell
   [Environment]::SetEnvironmentVariable("NGROK_AUTH_TOKEN", "your_token_here", "User")
   ```
   这样在新开 PowerShell 窗口后，`pyngrok` 会自动读取该变量。

2. **在代码中设置默认令牌**：
   打开 `app.py`，找到 `YOUR_NGROK_AUTH_TOKEN`，替换为您的真实令牌：
   ```python
   NGROK_AUTH_TOKEN = os.environ.get('NGROK_AUTH_TOKEN', 'your_token_here')
   ```

## Safety Features

- Secure compartment locking mechanism
- Real-time weight verification
- Automatic pill counting
- Session-based medication dispensing

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[Specify your license here]

## Support

For support, please [specify contact information or support channels]

## 查看服药历史

运行应用后，通过以下地址即可查看实时更新的服药历史记录：

```
http://<your_remote_domain>/history
``` 