from flask import Flask, render_template, request, jsonify
import serial
import threading
import time
import logging
import math 
import os
import requests
from pyngrok import ngrok, conf
import sqlite3

# Persist ngrok auth token to config file; no need to input every time
NGROK_AUTH_TOKEN = '2mFiHwvEfuSUrKTx1L8PkXEcKRK_ctEupzpfswsUSCBaj4Ac'
ngrok.set_auth_token(NGROK_AUTH_TOKEN)

# Cloud sync server URL, set via environment variable `CLOUD_SERVER_URL`
CLOUD_SERVER_URL = os.environ.get('CLOUD_SERVER_URL', 'https://your-cloud-server.com/api/consumption')

# Configuration
SERIAL_PORT = 'COM3'  # Modify as needed
BAUD_RATE = 9600

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)  # Set logging level
logger = logging.getLogger(__name__)

# --- Global State ---
arduino_raw_state = {  # Data directly from Arduino
    "stage_name": "Initializing",
    "total_weight_in_box_arduino": 0.0, 
    "pill_count_arduino_current_med": 0, 
    "current_med_on_arduino": "N/A",    
    "wpp_arduino_current_med": 0.25,    
    "lid_distance_cm": None,    # Lid distance
    "lid_open": False,         # Lid status
    "last_update": time.time(),
    "raw_data": ""
}
data_lock = threading.Lock() 
current_mode_is_simulation = True 
ser = None 

pc_managed_medication_details = {}
pc_active_medication_name = None

# Add sequential medication session state variables
medication_session_active = False
medication_session_data = {
    "start_weight": 0.0,
    "current_medication": None,
    "compartment_unlocked": False,
    "session_start_time": None
}
# --- End Global State ---

# Local history SQLite database
DB_PATH = os.environ.get('HISTORY_DB', 'history.db')
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    medication_name TEXT,
    pills_consumed INTEGER,
    weight_consumed REAL,
    session_duration REAL,
    timestamp INTEGER
)''')

# Add messages table
cursor.execute('''
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    sender TEXT DEFAULT 'Doctor',
    timestamp INTEGER
)''')

# --- Create medication reminders table ---
cursor.execute('''
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    medication_name TEXT NOT NULL,
    start_datetime INTEGER NOT NULL,
    end_datetime INTEGER NOT NULL,
    frequency_type TEXT NOT NULL,   -- 'interval' or 'daily'
    frequency_value REAL NOT NULL   -- Small time interval or daily count
)''')
conn.commit()

conn.commit()

def connect_to_arduino():
    global ser 
    try:
        if ser and ser.is_open: ser.close() 
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        logger.info(f"Attempting to connect to Arduino on {SERIAL_PORT}...")
        time.sleep(2) 
        if ser.is_open:
            logger.info(f"Successfully connected to Arduino on {SERIAL_PORT}")
            send_to_arduino_command(f"SET_MODE:{1 if current_mode_is_simulation else 0}") 
            if pc_active_medication_name and pc_active_medication_name in pc_managed_medication_details:
                sync_pc_active_med_to_arduino(pc_active_medication_name)
            return True
        return False
    except Exception as e:
        logger.error(f"Error connecting to Arduino: {e}")
        ser = None 
        return False

def read_from_arduino_thread_function():
    global arduino_raw_state, ser 
    logger.info("Starting Arduino listener thread.")
    connection_retries = 0
    last_reconnect_attempt = 0
    
    while True:
        # Check connection status, if not connected or last update exceeds 10 seconds, attempt to reconnect
        current_time = time.time()
        connection_lost = not (ser and ser.is_open) or (current_time - arduino_raw_state.get("last_update", 0) > 10)
        
        if connection_lost and current_time - last_reconnect_attempt > 5:  # At least 5 seconds between reconnection attempts
            last_reconnect_attempt = current_time
            connection_retries += 1
            logger.warning(f"Arduino connection lost or timeout, attempting to reconnect (Attempt {connection_retries})")
            
            # Close any existing old connection
            if ser and ser.is_open:
                try:
                    ser.close()
                except:
                    pass
                    
            # Attempt to reconnect
            if connect_to_arduino(): 
                connection_retries = 0
                logger.info("Arduino reconnection successful")
            else:
                logger.error("Arduino reconnection failed")
                # Brief sleep to avoid too frequent reconnection attempts
                time.sleep(1)
                continue
                
        try:
            if ser and ser.is_open and ser.in_waiting > 0: 
                line = ser.readline().decode('utf-8', errors='replace').strip()
                with data_lock: 
                    arduino_raw_state["last_update"] = time.time()
                    arduino_raw_state["raw_data"] = line
                if line.startswith("DATA:"): 
                    logger.info(f"Received DATA line: {line}")
                    parts = line[5:].split(',')
                    if len(parts) >= 5: 
                        with data_lock:
                            arduino_raw_state["stage_name"] = parts[0]
                            try: arduino_raw_state["total_weight_in_box_arduino"] = float(parts[1])
                            except ValueError: logger.warning(f"Unable to parse weight data: {parts[1]}")
                            try: arduino_raw_state["pill_count_arduino_current_med"] = int(parts[2])
                            except ValueError: logger.warning(f"Unable to parse pill count: {parts[2]}")
                            arduino_raw_state["current_med_on_arduino"] = parts[3]
                            try: arduino_raw_state["wpp_arduino_current_med"] = float(parts[4])
                            except ValueError: logger.warning(f"Unable to parse WPP: {parts[4]}")
                            # Parse ultrasonic sensor data: distance and status
                            if len(parts) >= 7:
                                try: arduino_raw_state["lid_distance_cm"] = float(parts[5])
                                except ValueError: arduino_raw_state["lid_distance_cm"] = None
                                try: arduino_raw_state["lid_open"] = bool(int(parts[6]))
                                except (ValueError, IndexError): arduino_raw_state["lid_open"] = False
                            
                            if arduino_raw_state["current_med_on_arduino"] == pc_active_medication_name and \
                               pc_active_medication_name in pc_managed_medication_details and \
                               abs(pc_managed_medication_details[pc_active_medication_name]['wpp'] - arduino_raw_state["wpp_arduino_current_med"]) > 0.0001: 
                                if "Measured single pill weight" in arduino_raw_state["raw_data"] or "MEASURE_SINGLE_PILL_WEIGHT" in arduino_raw_state["raw_data"]: 
                                    logger.info(f"Arduino reported new WPP value for '{pc_active_medication_name}': {arduino_raw_state['wpp_arduino_current_med']:.3f}g. Updating PC record.")
                                    pc_managed_medication_details[pc_active_medication_name]['wpp'] = arduino_raw_state["wpp_arduino_current_med"]
                                    recalculate_pill_count_for_med(pc_active_medication_name) 
                elif line.startswith("WEIGHT:"): 
                    # Handle response from GET_WEIGHT command
                    try:
                        weight_value = float(line.split(':')[1].strip())
                        with data_lock:
                            arduino_raw_state["total_weight_in_box_arduino"] = weight_value
                            arduino_raw_state["last_update"] = time.time()
                        logger.debug(f"Received weight data: {weight_value}g")
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Failed to parse weight data: {line}, error: {e}")
                elif "Arduino Pillbox Ready" in line: 
                    logger.info("Arduino confirmed ready")
                elif "Measuring sample" in line or "Starting measurement" in line:
                    # Record measurement process information
                    logger.info(f"Measurement info: {line}")
                elif line: 
                    logger.info(f"Arduino message: {line}") 
            else: 
                time.sleep(0.05)  # Brief sleep to avoid excessive CPU usage
        except serial.SerialException as e: 
            logger.error(f"Serial communication error: {e}. Closing port and will attempt to reconnect in next cycle.")
            try:
                if ser: 
                    ser.close()
            except:
                pass
            ser = None 
            time.sleep(1)  # Brief sleep after error
        except Exception as e: 
            logger.error(f"Arduino listener thread error: {e}")
            time.sleep(0.5)

def send_to_arduino_command(command_str):
    if ser and ser.is_open:
        try:
            logger.info(f"Sending to Arduino: {command_str}")
            ser.write((command_str + '\n').encode('utf-8')) 
            return True
        except Exception as e:
            logger.error(f"Error writing to serial port: {e}")
            return False
    logger.warning("Cannot send command: Serial port not connected.")
    return False

def recalculate_pill_count_for_med(med_name):
    if med_name in pc_managed_medication_details:
        details = pc_managed_medication_details[med_name]
        if details['wpp'] > 0.0001: 
            if details['total_weight_in_box'] < (details['wpp'] / 2.0): 
                details['count_in_box'] = 0
            else:
                details['count_in_box'] = int(round(details['total_weight_in_box'] / details['wpp'])) 
        else:
            details['count_in_box'] = 0 
        logger.debug(f"Recalculated PC count for {med_name}: {details['count_in_box']} (TotalW: {details['total_weight_in_box']:.2f}g, WPP: {details['wpp']:.3f}g)")

def sync_pc_active_med_to_arduino(med_name_to_sync):
    if med_name_to_sync and med_name_to_sync in pc_managed_medication_details:
        details = pc_managed_medication_details[med_name_to_sync]
        send_to_arduino_command(f"SELECT_MEDICATION:{med_name_to_sync}")
        time.sleep(0.05) 
        send_to_arduino_command(f"SET_PILL_WEIGHT:{details['wpp']:.4f}")
        time.sleep(0.05)
        if current_mode_is_simulation: 
            send_to_arduino_command(f"SET_WEIGHT:{details['total_weight_in_box']:.2f}")
        logger.info(f"Synced PC state for '{med_name_to_sync}' to Arduino (WPP: {details['wpp']:.3f}g, TotalW (if sim): {details['total_weight_in_box']:.2f}g).")
        return True
    logger.warning(f"Could not sync '{med_name_to_sync}' to Arduino: not found in PC details.")
    return False

@app.route('/')
def index():
    return render_template('index.html', initial_state={
        "is_simulation": current_mode_is_simulation,
        "pc_active_medication_name": pc_active_medication_name,
        "pc_managed_medication_details": dict(pc_managed_medication_details) 
    })

@app.route('/get_status')
def get_status_api():
    with data_lock: 
        status_to_send = {
            "arduino_state": dict(arduino_raw_state), 
            "is_simulation": current_mode_is_simulation,
            "pc_managed_medication_details": dict(pc_managed_medication_details), 
            "pc_active_medication_name": pc_active_medication_name
        }
        if time.time() - arduino_raw_state.get("last_update", 0) > 20 :
            status_to_send["arduino_state"]["stage_name"] = "Disconnected"
            status_to_send["arduino_state"]["raw_data"] = "Connection to Arduino potentially lost (stale data)."
    return jsonify(status_to_send)

@app.route('/set_mode/<mode_name>', methods=['POST'])
def set_mode_api(mode_name):
    global current_mode_is_simulation
    with data_lock: 
        if mode_name == "simulation": current_mode_is_simulation = True
        elif mode_name == "real": current_mode_is_simulation = False
        else: return jsonify({"status": "error", "message": "Invalid mode."}), 400
    send_to_arduino_command(f"SET_MODE:{1 if current_mode_is_simulation else 0}")
    if pc_active_medication_name: 
        sync_pc_active_med_to_arduino(pc_active_medication_name)
    msg = f"Switched to {mode_name.capitalize()} Mode."
    logger.info(msg)
    return jsonify({"status": "success", "message": msg, "is_simulation": current_mode_is_simulation})

@app.route('/set_stage/<int:stage_id>', methods=['POST'])
def set_stage_api(stage_id):
    if send_to_arduino_command(f"SET_STAGE:{stage_id}"):
        if stage_id == 2: # RESET_STAGE
            global pc_active_medication_name, medication_session_active, medication_session_data
            with data_lock:
                # Clear current active medication
                pc_active_medication_name = None
                
                # Clear all medication information (if complete reset is needed)
                pc_managed_medication_details.clear()
                
                # Clear local history
                try:
                    cursor.execute('DELETE FROM history')
                    conn.commit()
                    logger.info('Local medication history cleared')
                except Exception as e:
                    logger.error(f'Failed to clear local history: {e}')
                
                # Reset sequential medication session state
                medication_session_active = False
                medication_session_data = {
                    "start_weight": 0.0,
                    "current_medication": None,
                    "compartment_unlocked": False,
                    "session_start_time": None
                }
                
                # Reset Arduino state
                send_to_arduino_command("RESET_ALL")
                
            logger.info("System completely reset: cleared all medication information and session states")
        return jsonify({"status": "success", "message": f"Stage switch command sent (Stage ID: {stage_id}).", "stage_id": stage_id})
    return jsonify({"status": "error", "message": "Stage switch command failed to send."}), 500

@app.route('/add_or_update_known_medication', methods=['POST'])
def add_or_update_known_medication_api():
    global pc_managed_medication_details
    data = request.json
    med_name = data.get('name','').strip() 
    try:
        wpp = float(data.get('wpp', 0.0)) 
        if not med_name: 
            return jsonify({"status": "error", "message": "Medication name cannot be empty."}), 400
        if wpp < 0: 
             return jsonify({"status": "error", "message": "WPP cannot be negative."}), 400
        if wpp == 0.0 and data.get('wpp') is not None : 
            logger.info(f"WPP for '{med_name}' explicitly set to 0.0. It should be defined later via measurement or manual input.")
        with data_lock:
            if med_name not in pc_managed_medication_details: 
                pc_managed_medication_details[med_name] = {'wpp': wpp, 'total_weight_in_box': 0.0, 'count_in_box': 0}
                msg = f"Added new medication: '{med_name}' (Initial WPP: {wpp:.3f}g)."
            else: 
                pc_managed_medication_details[med_name]['wpp'] = wpp
                recalculate_pill_count_for_med(med_name) 
                msg = f"Updated WPP for '{med_name}' to {wpp:.3f}g. PC pill count recalculated."
                if med_name == pc_active_medication_name: 
                    send_to_arduino_command(f"SET_PILL_WEIGHT:{wpp:.4f}")
        logger.info(msg)
        return jsonify({"status": "success", "message": msg})
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid WPP value (must be a number)."}), 400

@app.route('/set_pc_active_medication', methods=['POST'])
def set_pc_active_medication_api():
    global pc_active_medication_name
    data = request.json
    med_name = data.get('name')
    with data_lock:
        if med_name and med_name in pc_managed_medication_details:
            pc_active_medication_name = med_name
            sync_pc_active_med_to_arduino(med_name) 
            msg = f"PC active medication set to: '{med_name}'. Synced with Arduino."
            logger.info(msg)
            return jsonify({"status": "success", "message": msg, "pc_active_medication_name": med_name})
        elif not med_name: 
            pc_active_medication_name = None
            logger.info("PC active medication cleared.")
            return jsonify({"status": "success", "message": "PC active medication cleared."})
        return jsonify({"status": "error", "message": f"Medication '{med_name}' not found in PC's known list."}), 404

@app.route('/set_simulated_total_weight_for_active_med', methods=['POST'])
def set_simulated_total_weight_api():
    if not current_mode_is_simulation:
        return jsonify({"status": "error", "message": "Operation only allowed in Simulation Mode."}), 403
    if not pc_active_medication_name:
        return jsonify({"status": "error", "message": "No PC active medication selected."}), 400
    try:
        weight = float(request.json.get('weight'))
        if weight < 0: return jsonify({"status": "error", "message": "Weight cannot be negative."}), 400
        with data_lock:
            if pc_active_medication_name in pc_managed_medication_details:
                pc_managed_medication_details[pc_active_medication_name]['total_weight_in_box'] = weight
                recalculate_pill_count_for_med(pc_active_medication_name) 
                send_to_arduino_command(f"SET_WEIGHT:{weight:.2f}") 
                details = pc_managed_medication_details[pc_active_medication_name]
                msg = f"Sim total weight for '{pc_active_medication_name}' set to {weight:.2f}g. PC count: {details['count_in_box']}."
                logger.info(msg)
                return jsonify({"status": "success", "message": msg})
            return jsonify({"status": "error", "message": "Active medication not found in details (internal error)."}), 500
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid weight value."}), 400

@app.route('/tare_arduino_sim_only', methods=['POST'])
def tare_arduino_sim_only_api():
    if not current_mode_is_simulation:
        logger.warning("TARE_ARDUINO_SIM_ONLY called in non-simulation mode. Sending TARE_SIM anyway.")
    if send_to_arduino_command("TARE_SIM"): 
        msg = "Arduino TARE_SIM command sent. Arduino's weight zeroed for next input."
        logger.info(msg)
        return jsonify({"status": "success", "message": msg})
    return jsonify({"status": "error", "message": "Failed to send TARE_SIM to Arduino."}), 500

@app.route('/update_state_from_manual_count_for_active_med', methods=['POST'])
def update_state_from_manual_count_api():
    if not pc_active_medication_name:
        return jsonify({"status": "error", "message": "No PC active medication selected."}), 400
    try:
        count = int(request.json.get('count'))
        if count < 0: return jsonify({"status": "error", "message": "Pill count cannot be negative."}), 400
        with data_lock:
            if pc_active_medication_name in pc_managed_medication_details:
                details = pc_managed_medication_details[pc_active_medication_name]
                wpp = details['wpp']
                if wpp <= 0.0001: 
                    return jsonify({"status": "error", "message": f"WPP for '{pc_active_medication_name}' is not valid (must be > 0.0001). Cannot calculate total weight."}), 400
                details['count_in_box'] = count
                details['total_weight_in_box'] = count * wpp 
                sync_pc_active_med_to_arduino(pc_active_medication_name) 
                msg = (f"For '{pc_active_medication_name}', count set to {count}. "
                       f"Calculated total weight: {details['total_weight_in_box']:.2f}g. Synced with Arduino.")
                logger.info(msg)
                return jsonify({"status": "success", "message": msg})
            return jsonify({"status": "error", "message": "Active medication not found in PC details (internal error)."}), 500
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid count value."}), 400

@app.route('/set_wpp_for_active_med_pc_and_arduino', methods=['POST'])
def set_wpp_for_active_med_pc_and_arduino_api():
    if not pc_active_medication_name:
        return jsonify({"status": "error", "message": "No PC active medication selected."}), 400
    try:
        wpp = float(request.json.get('wpp'))
        if wpp <= 0.0001: return jsonify({"status": "error", "message": "WPP must be positive and realistic (e.g. > 0.0001)."}), 400
        with data_lock:
            if pc_active_medication_name in pc_managed_medication_details:
                pc_managed_medication_details[pc_active_medication_name]['wpp'] = wpp
                recalculate_pill_count_for_med(pc_active_medication_name) 
                send_to_arduino_command(f"SET_PILL_WEIGHT:{wpp:.4f}") 
                details = pc_managed_medication_details[pc_active_medication_name]
                msg = f"WPP for '{pc_active_medication_name}' updated to {wpp:.3f}g. PC count: {details['count_in_box']}. Arduino notified."
                logger.info(msg)
                return jsonify({"status": "success", "message": msg})
            return jsonify({"status": "error", "message": "Active medication not found (internal error)."}), 500
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid WPP value."}), 400

@app.route('/measure_single_pill_real_mode_for_active_med', methods=['POST'])
def measure_single_pill_real_api():
    """Trigger Arduino to perform single pill weight measurement, and let frontend poll status to update WPP value"""
    global pc_active_medication_name
    # Ensure medication is selected
    if not pc_active_medication_name:
        return jsonify({"status": "error", "message": "Please select a medication to measure first."}), 400
    # Check mode
    if current_mode_is_simulation:
        return jsonify({"status": "error", "message": "Currently in simulation mode, please switch to real mode before measuring."}), 400
    # Send measurement command to Arduino
    if not send_to_arduino_command("MEASURE_SINGLE_PILL_WEIGHT"):
        return jsonify({"status": "error", "message": "Unable to send measurement command to Arduino"}), 500
    # Command sent, frontend will poll status to detect and update WPP
    return jsonify({"status": "success", "message": "Measurement command sent, please wait for results."}), 200

@app.route('/consume_pills_for_active_med', methods=['POST'])
def consume_pills_pc_api():
    if not pc_active_medication_name:
        return jsonify({"status": "error", "message": "No PC active medication selected to consume from."}), 400
    try:
        num_to_consume = int(request.json.get('count'))
        if num_to_consume <= 0: return jsonify({"status": "error", "message": "Number of pills must be positive."}), 400
        with data_lock:
            if pc_active_medication_name in pc_managed_medication_details:
                details = pc_managed_medication_details[pc_active_medication_name]
                wpp = details['wpp']
                if wpp <= 0.0001: 
                    return jsonify({"status": "error", "message": f"WPP for '{pc_active_medication_name}' is not valid. Cannot consume."}), 400
                weight_to_reduce = num_to_consume * wpp
                current_total_weight = details['total_weight_in_box']
                if current_total_weight >= weight_to_reduce - (wpp / 2.0):
                    details['total_weight_in_box'] = max(0.0, current_total_weight - weight_to_reduce) 
                    recalculate_pill_count_for_med(pc_active_medication_name) 
                    sync_pc_active_med_to_arduino(pc_active_medication_name)
                    time.sleep(0.1) 
                    if send_to_arduino_command(f"CONSUME_PILLS:{num_to_consume}"): 
                        msg = (f"{num_to_consume} pills of '{pc_active_medication_name}' consumed (PC records updated). "
                               f"New PC total weight: {details['total_weight_in_box']:.2f}g, PC count: {details['count_in_box']}.")
                        logger.info(msg)
                        return jsonify({"status": "success", "message": msg, "consumed_med": pc_active_medication_name, "consumed_count": num_to_consume}) # Return consumed info
                    else: 
                        details['total_weight_in_box'] = current_total_weight 
                        recalculate_pill_count_for_med(pc_active_medication_name)
                        return jsonify({"status": "error", "message": "Failed to send CONSUME_PILLS command to Arduino. PC state change reverted."}), 500
                else:
                    return jsonify({"status": "error", "message": f"Not enough '{pc_active_medication_name}' on PC records (by weight) to consume {num_to_consume}."}), 400
            return jsonify({"status": "error", "message": "Active medication details not found on PC (internal error)."}), 500
    except (TypeError, ValueError) as e:
        logger.error(f"Error in consume_pills_pc_api: {e}")
        return jsonify({"status": "error", "message": "Invalid input for number of pills."}), 400

@app.route('/consume_pills_by_weight_simulated', methods=['POST'])
def consume_pills_by_weight_simulated_api():
    if not current_mode_is_simulation:
        return jsonify({"status": "error", "message": "Consume by weight is a simulation-only feature."}), 403
    if not pc_active_medication_name:
        return jsonify({"status": "error", "message": "No PC active medication selected."}), 400
    
    try:
        weight_to_reduce_str = request.json.get('weight_to_reduce')
        if not weight_to_reduce_str:
            return jsonify({"status": "error", "message": "Weight to reduce is missing."}), 400
        weight_to_reduce = float(weight_to_reduce_str)
        if weight_to_reduce <= 0:
            return jsonify({"status": "error", "message": "Weight to reduce must be positive."}), 400

        with data_lock:
            if pc_active_medication_name in pc_managed_medication_details:
                details = pc_managed_medication_details[pc_active_medication_name]
                wpp = details['wpp']
                if wpp <= 0.0001:
                    return jsonify({"status": "error", "message": f"WPP for '{pc_active_medication_name}' is not valid ({wpp:.4f}g). Cannot calculate pills to consume."}), 400

                if weight_to_reduce < (wpp / 2.0):
                    num_to_consume = 0
                else:
                    num_to_consume = int(round(weight_to_reduce / wpp))

                if num_to_consume == 0:
                    return jsonify({"status": "info", "message": f"Weight reduction {weight_to_reduce:.2f}g is less than half a pill's weight. No pills consumed."}), 200 
                
                actual_weight_to_reduce = num_to_consume * wpp
                current_total_weight = details['total_weight_in_box']

                if current_total_weight >= actual_weight_to_reduce - (wpp / 2.0): 
                    details['total_weight_in_box'] = max(0.0, current_total_weight - actual_weight_to_reduce)
                    recalculate_pill_count_for_med(pc_active_medication_name)
                    
                    sync_pc_active_med_to_arduino(pc_active_medication_name)
                    time.sleep(0.1)

                    if send_to_arduino_command(f"CONSUME_PILLS:{num_to_consume}"):
                        msg = (f"Consumed approx. {num_to_consume} pills of '{pc_active_medication_name}' (by reducing {weight_to_reduce:.2f}g). "
                               f"PC total weight: {details['total_weight_in_box']:.2f}g, PC count: {details['count_in_box']}.")
                        logger.info(msg)
                        return jsonify({"status": "success", "message": msg, "consumed_med": pc_active_medication_name, "consumed_count": num_to_consume, "weight_reduced_approx": actual_weight_to_reduce })
                    else:
                        details['total_weight_in_box'] = current_total_weight
                        recalculate_pill_count_for_med(pc_active_medication_name)
                        return jsonify({"status": "error", "message": "Failed to send CONSUME_PILLS command to Arduino after weight calculation. PC state reverted."}), 500
                else:
                    return jsonify({"status": "error", "message": f"Not enough '{pc_active_medication_name}' (calculated {num_to_consume} pills) to consume by reducing {weight_to_reduce:.2f}g."}), 400
            return jsonify({"status": "error", "message": "Active medication details not found on PC."}), 500
    except (TypeError, ValueError) as e:
        logger.error(f"Error in consume_pills_by_weight_simulated_api: {e}")
        return jsonify({"status": "error", "message": "Invalid input for weight to reduce."}), 400

# --- Sequential Medication Session API ---
@app.route('/start_medication_session', methods=['POST'])
def start_medication_session_api():
    global medication_session_active, medication_session_data
    
    data = request.json
    medication_name = data.get('medication_name')
    
    if not medication_name:
        return jsonify({"status": "error", "message": "Must specify the medication name to be taken"}), 400
    
    if medication_name not in pc_managed_medication_details:
        return jsonify({"status": "error", "message": f"Medication not found: {medication_name}"}), 404
    
    with data_lock:
        if medication_session_active:
            return jsonify({"status": "error", "message": "There is already an active medication session in progress, please finish the current session first"}), 400
        
        # Set PC current active medication
        global pc_active_medication_name
        pc_active_medication_name = medication_name
        
        # Sync to Arduino
        sync_pc_active_med_to_arduino(medication_name)
        
        # New: Send BOX_TARE command, let Arduino record box baseline weight
        send_to_arduino_command('BOX_TARE')
        
        # Record initial weight, set to 0 after peeling
        medication_session_data = {
            "start_weight": 0.0,
            "current_medication": medication_name,
            "compartment_unlocked": False,
            "session_start_time": time.time()
        }
        
        medication_session_active = True
        
        logger.info(f"Started '{medication_name}' medication session, initial weight: {medication_session_data['start_weight']:.2f}g")
        
        return jsonify({
            "status": "success", 
            "message": f"Started '{medication_name}' medication session",
            "session_data": medication_session_data
        })

@app.route('/unlock_medication_compartment', methods=['POST'])
def unlock_medication_compartment_api():
    global medication_session_data
    
    if not medication_session_active:
        return jsonify({"status": "error", "message": "No active medication session in progress, please start a session first"}), 400
    
    with data_lock:
        # In real mode, send unlock command to Arduino
        if not current_mode_is_simulation:
            if not send_to_arduino_command("UNLOCK_COMPARTMENT:1"):
                return jsonify({"status": "error", "message": "Unable to send unlock command to Arduino"}), 500
        
        medication_session_data["compartment_unlocked"] = True
        logger.info(f"Medication compartment unlocked, ready to take '{medication_session_data['current_medication']}'")
        
        return jsonify({
            "status": "success", 
            "message": f"Medication compartment unlocked for '{medication_session_data['current_medication']}'",
            "session_data": medication_session_data
        })

@app.route('/lock_and_record_consumption', methods=['POST'])
def lock_and_record_consumption_api():
    global medication_session_active, medication_session_data, pc_managed_medication_details
    
    if not medication_session_active:
        return jsonify({"status": "error", "message": "No active medication session in progress, please start a session first"}), 400
    
    if not medication_session_data["compartment_unlocked"]:
        return jsonify({"status": "error", "message": "Medication compartment not unlocked, please unlock compartment first"}), 400
    
    with data_lock:
        # In real mode, send lock command to Arduino
        if not current_mode_is_simulation:
            if not send_to_arduino_command("LOCK_COMPARTMENT:1"):
                return jsonify({"status": "error", "message": "Unable to send lock command to Arduino"}), 500
        
        # Calculate consumed weight and pill count (directly use the absolute value of the current adjusted weight)
        med_name = medication_session_data["current_medication"]
        current_weight = arduino_raw_state["total_weight_in_box_arduino"]
        weight_consumed = abs(current_weight)
        
        # Calculate consumed pill count based on WPP
        med_details = pc_managed_medication_details[med_name]
        wpp = med_details["wpp"]
        pills_consumed = int(round(weight_consumed / wpp)) if wpp > 0.0001 else 0
        
        # Update medication inventory
        if pills_consumed > 0:
            med_details["count_in_box"] = max(0, med_details["count_in_box"] - pills_consumed)
            med_details["total_weight_in_box"] = max(0, med_details["total_weight_in_box"] - (pills_consumed * wpp))
            
            # Sync to Arduino
            if current_mode_is_simulation:
                send_to_arduino_command(f"SET_WEIGHT:{med_details['total_weight_in_box']:.2f}")
        
        # Reset session
        medication_session_active = False
        session_duration = time.time() - medication_session_data["session_start_time"]
        
        logger.info(f"Completed medication session for '{med_name}': consumed {pills_consumed} pills, weight reduced: {weight_consumed:.2f}g, duration: {session_duration:.1f}s")
        
        # Save session data for return
        completed_session = medication_session_data.copy()
        completed_session.update({
            "end_weight": current_weight,
            "weight_consumed": weight_consumed,
            "pills_consumed": pills_consumed,
            "session_duration": session_duration
        })
        
        # New: Asynchronously sync to cloud server, avoid blocking main thread
        cloud_payload = {
            "medication_name": med_name,
            "pills_consumed": pills_consumed,
            "weight_consumed": weight_consumed,
            "session_duration": session_duration,
            "timestamp": time.time()
        }
        def _sync_to_cloud(payload):
            try:
                # Skip default placeholder address
                if CLOUD_SERVER_URL and "your-cloud-server.com" not in CLOUD_SERVER_URL:
                    requests.post(CLOUD_SERVER_URL, json=payload, timeout=2)
                    logger.info("Medication consumption record asynchronously synced to cloud server")
                else:
                    logger.info("Skipped default cloud sync address, please configure valid CLOUD_SERVER_URL")
            except Exception as e:
                logger.error(f"Asynchronous sync to cloud server failed: {e}")
        threading.Thread(target=_sync_to_cloud, args=(cloud_payload,), daemon=True).start()

        # Save local history record
        try:
            cursor.execute(
                'INSERT INTO history (medication_name, pills_consumed, weight_consumed, session_duration, timestamp) VALUES (?, ?, ?, ?, ?)',
                (med_name, pills_consumed, weight_consumed, session_duration, int(time.time()))
            )
            conn.commit()
            logger.info('Medication consumption record saved to local history database')
        except Exception as e:
            logger.error(f"Failed to save local history: {e}")
        
        # Reset session data
        medication_session_data = {
            "start_weight": 0.0,
            "current_medication": None,
            "compartment_unlocked": False,
            "session_start_time": None
        }
        
        return jsonify({
            "status": "success", 
            "message": f"Completed consumption record: {med_name} {pills_consumed} pills",
            "completed_session": completed_session,
            "consumed_med": med_name,
            "consumed_count": pills_consumed,
            "weight_reduced_approx": weight_consumed
        })

@app.route('/cancel_medication_session', methods=['POST'])
def cancel_medication_session_api():
    global medication_session_active, medication_session_data
    
    if not medication_session_active:
        return jsonify({"status": "error", "message": "No active medication session to cancel"}), 400
    
    with data_lock:
        # If compartment is unlocked, send lock command to Arduino
        if medication_session_data["compartment_unlocked"] and not current_mode_is_simulation:
            send_to_arduino_command("LOCK_COMPARTMENT:1")
        
        # Save session data for return
        cancelled_session = medication_session_data.copy()
        
        # Reset session
        medication_session_active = False
        medication_session_data = {
            "start_weight": 0.0,
            "current_medication": None,
            "compartment_unlocked": False,
            "session_start_time": None
        }
        
        logger.info(f"Cancelled medication session: '{cancelled_session['current_medication']}'")
        
        return jsonify({
            "status": "success", 
            "message": f"Cancelled medication session: {cancelled_session['current_medication']}",
            "cancelled_session": cancelled_session
        })

@app.route('/get_medication_session_status', methods=['GET'])
def get_medication_session_status_api():
    with data_lock:
        return jsonify({
            "session_active": medication_session_active,
            "session_data": medication_session_data
        })

@app.route('/get_current_weight', methods=['GET'])
def get_current_weight():
    """Return current weight from cached state."""
    with data_lock:
        weight = arduino_raw_state.get('total_weight_in_box_arduino', 0.0)
        last_update = arduino_raw_state.get('last_update', time.time())
    age = time.time() - last_update
    return jsonify({
        'status': 'success',
        'weight': weight,
        'last_update': last_update,
        'age': age
    })

@app.route('/force_refresh_weight', methods=['POST'])
def force_refresh_weight():
    """Force get latest weight data, for drug inventory setup step"""
    try:
        # Parse JSON safely
        data = request.get_json(silent=True) or {}
        # If real mode and port not connected, try reconnect
        if not current_mode_is_simulation and (ser is None or not ser.is_open):
            logger.warning("force_refresh_weight: Serial port not connected, attempting to reconnect Arduino")
            if not connect_to_arduino():
                return jsonify({'status': 'error', 'message': 'Arduino reconnection failed'}), 500
        if not current_mode_is_simulation and ser and ser.is_open:
            # Clear buffer
            ser.reset_input_buffer()
            
            # First execute peeling operation
            if data.get('tare_first', False):
                logger.info("Force refresh before executing peeling operation")
                ser.write(b"TARE_SIM\n")
                time.sleep(0.5)  # Wait for peeling to complete
            
            # Multiple attempts to get valid weight
            max_attempts = 3
            for attempt in range(max_attempts):
                # Send GET_WEIGHT command
                ser.write(b"GET_WEIGHT\n")
                
                # Wait for response
                response_timeout = 2.0  # Longer timeout time
                start_time = time.time()
                
                while time.time() - start_time < response_timeout:
                    if ser.in_waiting > 0:
                        line = ser.readline().decode('utf-8', errors='replace').strip()
                        logger.debug(f"Force refresh received response: {line}")
                        
                        if line.startswith("WEIGHT:"):
                            try:
                                weight_value = float(line.split(':')[1].strip())
                                
                                # Confirm weight is valid value
                                if weight_value >= 0:
                                    with data_lock:
                                        arduino_raw_state["total_weight_in_box_arduino"] = weight_value
                                        arduino_raw_state["last_update"] = time.time()
                                    
                                    # If active medication, update inventory calculation
                                    if pc_active_medication_name and pc_active_medication_name in pc_managed_medication_details:
                                        med_details = pc_managed_medication_details[pc_active_medication_name]
                                        if med_details['wpp'] > 0.001:
                                            med_details['total_weight_in_box'] = weight_value
                                            recalculate_pill_count_for_med(pc_active_medication_name)
                                            logger.info(f"Updated '{pc_active_medication_name}' inventory: {med_details['count_in_box']} pills (TotalW {weight_value:.3f}g)")
                                    
                                    return jsonify({
                                        'status': 'success',
                                        'weight': weight_value,
                                        'message': f"Successfully got real-time weight: {weight_value:.3f}g",
                                        'attempt': attempt + 1
                                    })
                            except (ValueError, IndexError) as e:
                                logger.warning(f"Failed to parse weight response: {line}, error: {e}")
                    
                    time.sleep(0.05)
                
                logger.warning(f"Force refresh weight attempt {attempt+1}/{max_attempts} timed out")
                time.sleep(0.2)  # Brief delay before retrying
            
            # All attempts failed
            return jsonify({
                'status': 'error',
                'message': f"Failed to get valid weight data, please check sensor connection",
                'weight': 0.0
            }), 500
        else:
            # Simulation mode, directly return current simulated weight
            with data_lock:
                weight = arduino_raw_state.get('total_weight_in_box_arduino', 0.0)
            
            return jsonify({
                'status': 'success',
                'weight': weight,
                'message': f"Simulation mode weight: {weight:.3f}g"
            })
    
    except Exception as e:
        error_msg = f"Error occurred during force refresh weight: {str(e)}"
        logger.error(error_msg)
        return jsonify({'status': 'error', 'message': error_msg, 'weight': 0.0}), 500

@app.route('/inventory_setup.html')
def inventory_setup_page():
    """Return inventory setup page"""
    return render_template('inventory_setup.html')

@app.route('/medication_setup.html')
def medication_setup_page():
    """Return medication setup page (if not exist, create a fake page)"""
    return render_template('inventory_setup.html')  # Temporary use same page

@app.route('/api/history', methods=['GET'])
def api_history():
    try:
        # Use a fresh cursor/connection to avoid recursive use
        rows = conn.execute(
            'SELECT medication_name, pills_consumed, weight_consumed, session_duration, timestamp '
            'FROM history ORDER BY timestamp DESC'
        ).fetchall()
        history_list = [{
            'medication_name': r[0],
            'pills_consumed': r[1],
            'weight_consumed': r[2],
            'session_duration': r[3],
            'timestamp': r[4]
        } for r in rows]
        return jsonify(history_list)
    except Exception as e:
        logger.error(f"Error querying history: {e}")
        # Return empty list on error
        return jsonify([])

@app.route('/history')
def history_page():
    return render_template('history.html')

@app.route('/remote')
def remote_monitor_page():
    return render_template('remote_monitor.html')

# Add messages related API
@app.route('/api/messages', methods=['GET'])
def get_messages():
    cursor.execute('SELECT id, content, sender, timestamp FROM messages ORDER BY timestamp DESC LIMIT 50')
    rows = cursor.fetchall()
    messages = [{
        'id': r[0],
        'content': r[1],
        'sender': r[2],
        'timestamp': r[3]
    } for r in rows]
    return jsonify(messages)

@app.route('/api/messages', methods=['POST'])
def add_message():
    data = request.json
    if not data or 'content' not in data:
        return jsonify({'status': 'error', 'message': 'Message content cannot be empty'}), 400
    
    content = data.get('content').strip()
    sender = data.get('sender', 'Doctor').strip()
    
    if not content:
        return jsonify({'status': 'error', 'message': 'Message content cannot be empty'}), 400
    
    timestamp = int(time.time())
    
    try:
        cursor.execute(
            'INSERT INTO messages (content, sender, timestamp) VALUES (?, ?, ?)',
            (content, sender, timestamp)
        )
        conn.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Message added',
            'id': cursor.lastrowid,
            'content': content,
            'sender': sender,
            'timestamp': timestamp
        })
    except Exception as e:
        logger.error(f"Failed to add message: {e}")
        return jsonify({'status': 'error', 'message': f'Failed to add message: {str(e)}'}), 500

# --- Reminder related API ---
@app.route('/api/reminders', methods=['GET'])
def get_reminders():
    cursor.execute('SELECT id, medication_name, start_datetime, end_datetime, frequency_type, frequency_value FROM reminders')
    rows = cursor.fetchall()
    reminders = []
    for r in rows:
        reminders.append({
            'id': r[0],
            'medication_name': r[1],
            'start_datetime': r[2],
            'end_datetime': r[3],
            'frequency_type': r[4],
            'frequency_value': r[5]
        })
    return jsonify(reminders)

@app.route('/api/reminders', methods=['POST'])
def add_reminder():
    data = request.json or {}
    name = data.get('medication_name')
    sd = data.get('start_datetime')
    ed = data.get('end_datetime')
    ftype = data.get('frequency_type')
    fval = data.get('frequency_value')
    if not name or sd is None or ed is None or ftype not in ('interval','daily') or not fval:
        return jsonify({'status':'error','message':'Invalid parameters'}), 400
    cursor.execute('INSERT INTO reminders (medication_name,start_datetime,end_datetime,frequency_type,frequency_value) VALUES (?,?,?,?,?)',
                   (name, int(sd), int(ed), ftype, float(fval)))
    conn.commit()
    return jsonify({'status':'success','id': cursor.lastrowid})

# Add /calendar page
@app.route('/calendar')
def calendar_page():
    return render_template('calendar.html')

# --- app.py end ---
if __name__ == '__main__':
    logger.info("Starting Flask Pillbox Controller.")

    # 1. Create ngrok tunnel
    try:
        from pyngrok import ngrok, conf

        # If in Australia, optionally set region, reduce latency
        conf.get_default().region = "ap"   # Can also leave empty for ngrok to auto-select

        public_url = ngrok.connect(addr=5000, proto="http").public_url
        logger.info(f"ngrok tunnel created: {public_url}")
        logger.info(f"Remote monitoring page address: {public_url}/remote")
    except Exception as e:
        logger.error(f"Failed to create ngrok tunnel: {e}")

    # 2. Start Arduino listener thread
    if not connect_to_arduino(): 
        logger.warning("Failed to connect to Arduino at startup, listener thread will retry continuously.")
    threading.Thread(target=read_from_arduino_thread_function,
                     daemon=True).start()

    # 3. Start Flask
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
