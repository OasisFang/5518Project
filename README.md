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