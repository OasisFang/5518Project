from flask import Flask, render_template, request, jsonify
import serial
import threading
import time
import logging
import math 

# 配置
SERIAL_PORT = 'COM3' # 根据实际情况修改
BAUD_RATE = 9600

app = Flask(__name__)
logging.basicConfig(level=logging.INFO) # 设置日志级别
logger = logging.getLogger(__name__)

# --- 全局状态 ---
arduino_raw_state = { # 直接来自 Arduino 的数据
    "stage_name": "Initializing",
    "total_weight_in_box_arduino": 0.0, 
    "pill_count_arduino_current_med": 0, 
    "current_med_on_arduino": "N/A",    
    "wpp_arduino_current_med": 0.25,    
    "last_update": time.time(),
    "raw_data": ""
}
data_lock = threading.Lock() 
current_mode_is_simulation = True 
ser = None 

pc_managed_medication_details = {}
pc_active_medication_name = None

# 添加顺序服药会话状态变量
medication_session_active = False
medication_session_data = {
    "start_weight": 0.0,
    "current_medication": None,
    "compartment_unlocked": False,
    "session_start_time": None
}
# --- End 全局状态 ---

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
        # 检查连接状态，如果没有连接或者最后更新时间超过10秒，尝试重连
        current_time = time.time()
        connection_lost = not (ser and ser.is_open) or (current_time - arduino_raw_state.get("last_update", 0) > 10)
        
        if connection_lost and current_time - last_reconnect_attempt > 5:  # 至少5秒间隔重连尝试
            last_reconnect_attempt = current_time
            connection_retries += 1
            logger.warning(f"Arduino连接丢失或超时，尝试重连 (第{connection_retries}次)")
            
            # 关闭可能存在的旧连接
            if ser and ser.is_open:
                try:
                    ser.close()
                except:
                    pass
                    
            # 尝试重新连接
            if connect_to_arduino(): 
                connection_retries = 0
                logger.info("Arduino重连成功")
            else:
                logger.error("Arduino重连失败")
                # 短暂休眠避免过于频繁的重连尝试
                time.sleep(1)
                continue
                
        try:
            if ser and ser.is_open and ser.in_waiting > 0: 
                line = ser.readline().decode('utf-8', errors='replace').strip()
                with data_lock: 
                    arduino_raw_state["last_update"] = time.time()
                    arduino_raw_state["raw_data"] = line
                if line.startswith("DATA:"): 
                    parts = line[5:].split(',')
                    if len(parts) == 5: 
                        with data_lock:
                            arduino_raw_state["stage_name"] = parts[0]
                            try: arduino_raw_state["total_weight_in_box_arduino"] = float(parts[1])
                            except ValueError: logger.warning(f"无法解析重量数据: {parts[1]}")
                            try: arduino_raw_state["pill_count_arduino_current_med"] = int(parts[2])
                            except ValueError: logger.warning(f"无法解析药片数量: {parts[2]}")
                            arduino_raw_state["current_med_on_arduino"] = parts[3]
                            try: arduino_raw_state["wpp_arduino_current_med"] = float(parts[4])
                            except ValueError: logger.warning(f"无法解析WPP: {parts[4]}")
                            
                            if arduino_raw_state["current_med_on_arduino"] == pc_active_medication_name and \
                               pc_active_medication_name in pc_managed_medication_details and \
                               abs(pc_managed_medication_details[pc_active_medication_name]['wpp'] - arduino_raw_state["wpp_arduino_current_med"]) > 0.0001: 
                                if "Measured single pill weight" in arduino_raw_state["raw_data"] or "MEASURE_SINGLE_PILL_WEIGHT" in arduino_raw_state["raw_data"]: 
                                    logger.info(f"Arduino报告了'{pc_active_medication_name}'的新WPP值: {arduino_raw_state['wpp_arduino_current_med']:.3f}g. 更新PC记录。")
                                    pc_managed_medication_details[pc_active_medication_name]['wpp'] = arduino_raw_state["wpp_arduino_current_med"]
                                    recalculate_pill_count_for_med(pc_active_medication_name) 
                elif line.startswith("WEIGHT:"): 
                    # 处理来自GET_WEIGHT命令的响应
                    try:
                        weight_value = float(line.split(':')[1].strip())
                        with data_lock:
                            arduino_raw_state["total_weight_in_box_arduino"] = weight_value
                            arduino_raw_state["last_update"] = time.time()
                        logger.debug(f"接收到重量数据: {weight_value}g")
                    except (ValueError, IndexError) as e:
                        logger.warning(f"解析重量数据失败: {line}, 错误: {e}")
                elif "Arduino Pillbox Ready" in line: 
                    logger.info("Arduino确认就绪")
                elif "测量样本" in line or "开始测量" in line:
                    # 记录测量过程信息
                    logger.info(f"测量信息: {line}")
                elif line: 
                    logger.info(f"Arduino消息: {line}") 
            else: 
                time.sleep(0.05)  # 短暂休眠，避免过度占用CPU
        except serial.SerialException as e: 
            logger.error(f"串口通信错误: {e}. 关闭端口并将在下一循环尝试重连。")
            try:
                if ser: 
                    ser.close()
            except:
                pass
            ser = None 
            time.sleep(1)  # 错误后短暂休眠
        except Exception as e: 
            logger.error(f"Arduino监听线程错误: {e}")
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
                # 清除当前活动药物
                pc_active_medication_name = None
                
                # 清除所有药物信息（如果需要完全重置）
                pc_managed_medication_details.clear()
                
                # 重置顺序服药会话状态
                medication_session_active = False
                medication_session_data = {
                    "start_weight": 0.0,
                    "current_medication": None,
                    "compartment_unlocked": False,
                    "session_start_time": None
                }
                
                # 重置Arduino状态
                send_to_arduino_command("RESET_ALL")
                
            logger.info("系统已完全重置：清除了所有药物信息和会话状态")
        return jsonify({"status": "success", "message": f"阶段切换命令已发送 (阶段 ID: {stage_id})。", "stage_id": stage_id})
    return jsonify({"status": "error", "message": "阶段切换命令发送失败"}), 500

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
    # 暂时禁用单片测量功能，避免缩进错误影响应用启动
    return jsonify({"status": "error", "message": "Measure single pill disabled"}), 501

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

# --- 顺序服药流程相关API ---
@app.route('/start_medication_session', methods=['POST'])
def start_medication_session_api():
    global medication_session_active, medication_session_data
    
    data = request.json
    medication_name = data.get('medication_name')
    
    if not medication_name:
        return jsonify({"status": "error", "message": "必须指定要服用的药物名称"}), 400
    
    if medication_name not in pc_managed_medication_details:
        return jsonify({"status": "error", "message": f"未找到药物: {medication_name}"}), 404
    
    with data_lock:
        if medication_session_active:
            return jsonify({"status": "error", "message": "已有一个服药会话正在进行中，请先结束当前会话"}), 400
        
        # 设置PC当前活动药物
        global pc_active_medication_name
        pc_active_medication_name = medication_name
        
        # 同步到Arduino
        sync_pc_active_med_to_arduino(medication_name)
        
        # 记录初始重量
        medication_session_data = {
            "start_weight": arduino_raw_state["total_weight_in_box_arduino"],
            "current_medication": medication_name,
            "compartment_unlocked": False,
            "session_start_time": time.time()
        }
        
        medication_session_active = True
        
        logger.info(f"开始 '{medication_name}' 的服药会话，初始重量: {medication_session_data['start_weight']:.2f}g")
        
        return jsonify({
            "status": "success", 
            "message": f"已开始 '{medication_name}' 的服药会话",
            "session_data": medication_session_data
        })

@app.route('/unlock_medication_compartment', methods=['POST'])
def unlock_medication_compartment_api():
    global medication_session_data
    
    if not medication_session_active:
        return jsonify({"status": "error", "message": "没有活动的服药会话，请先开始一个会话"}), 400
    
    with data_lock:
        # 在真实模式下，发送解锁命令到Arduino
        if not current_mode_is_simulation:
            if not send_to_arduino_command("UNLOCK_COMPARTMENT:1"):
                return jsonify({"status": "error", "message": "无法发送解锁命令到Arduino"}), 500
        
        medication_session_data["compartment_unlocked"] = True
        logger.info(f"已解锁药格，准备取出 '{medication_session_data['current_medication']}'")
        
        return jsonify({
            "status": "success", 
            "message": f"已解锁 '{medication_session_data['current_medication']}' 的药格",
            "session_data": medication_session_data
        })

@app.route('/lock_and_record_consumption', methods=['POST'])
def lock_and_record_consumption_api():
    global medication_session_active, medication_session_data, pc_managed_medication_details
    
    if not medication_session_active:
        return jsonify({"status": "error", "message": "没有活动的服药会话，请先开始一个会话"}), 400
    
    if not medication_session_data["compartment_unlocked"]:
        return jsonify({"status": "error", "message": "药格尚未解锁，请先解锁药格"}), 400
    
    with data_lock:
        # 在真实模式下，发送锁定命令到Arduino
        if not current_mode_is_simulation:
            if not send_to_arduino_command("LOCK_COMPARTMENT:1"):
                return jsonify({"status": "error", "message": "无法发送锁定命令到Arduino"}), 500
        
        # 计算消耗的重量和药片数量
        med_name = medication_session_data["current_medication"]
        start_weight = medication_session_data["start_weight"]
        current_weight = arduino_raw_state["total_weight_in_box_arduino"]
        weight_consumed = max(0, start_weight - current_weight)  # 防止负数
        
        # 根据WPP计算消耗的药片数量
        med_details = pc_managed_medication_details[med_name]
        wpp = med_details["wpp"]
        if wpp > 0.001:  # 防止除以非常小的数
            pills_consumed = round(weight_consumed / wpp)
        else:
            pills_consumed = 0
        
        # 更新药物库存
        if pills_consumed > 0:
            med_details["count_in_box"] = max(0, med_details["count_in_box"] - pills_consumed)
            med_details["total_weight_in_box"] = max(0, med_details["total_weight_in_box"] - (pills_consumed * wpp))
            
            # 同步到Arduino
            if current_mode_is_simulation:
                send_to_arduino_command(f"SET_WEIGHT:{med_details['total_weight_in_box']:.2f}")
        
        # 重置会话
        medication_session_active = False
        session_duration = time.time() - medication_session_data["session_start_time"]
        
        logger.info(f"已完成 '{med_name}' 的服药会话，消耗: {pills_consumed} 片，重量减少: {weight_consumed:.2f}g，持续时间: {session_duration:.1f}秒")
        
        # 保存会话数据用于返回
        completed_session = medication_session_data.copy()
        completed_session.update({
            "end_weight": current_weight,
            "weight_consumed": weight_consumed,
            "pills_consumed": pills_consumed,
            "session_duration": session_duration
        })
        
        # 重置会话数据
        medication_session_data = {
            "start_weight": 0.0,
            "current_medication": None,
            "compartment_unlocked": False,
            "session_start_time": None
        }
        
        return jsonify({
            "status": "success", 
            "message": f"已完成服药记录: {med_name} {pills_consumed} 片",
            "completed_session": completed_session,
            "consumed_med": med_name,
            "consumed_count": pills_consumed,
            "weight_reduced_approx": weight_consumed
        })

@app.route('/cancel_medication_session', methods=['POST'])
def cancel_medication_session_api():
    global medication_session_active, medication_session_data
    
    if not medication_session_active:
        return jsonify({"status": "error", "message": "没有活动的服药会话可取消"}), 400
    
    with data_lock:
        # 如果药格已解锁，发送锁定命令到Arduino
        if medication_session_data["compartment_unlocked"] and not current_mode_is_simulation:
            send_to_arduino_command("LOCK_COMPARTMENT:1")
        
        # 保存会话数据用于返回
        cancelled_session = medication_session_data.copy()
        
        # 重置会话
        medication_session_active = False
        medication_session_data = {
            "start_weight": 0.0,
            "current_medication": None,
            "compartment_unlocked": False,
            "session_start_time": None
        }
        
        logger.info(f"已取消服药会话: '{cancelled_session['current_medication']}'")
        
        return jsonify({
            "status": "success", 
            "message": f"已取消服药会话: {cancelled_session['current_medication']}",
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
    # 直接返回缓存的重量状态，避免串口并发读取冲突
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
    """强制获取最新重量数据，用于药物库存设置步骤"""
    try:
        # 解析 JSON safely
        data = request.get_json(silent=True) or {}
        # 如果是真实模式且串口未连接，尝试重连
        if not current_mode_is_simulation and (ser is None or not ser.is_open):
            logger.warning("force_refresh_weight: 串口未连接，尝试重新连接 Arduino")
            if not connect_to_arduino():
                return jsonify({'status': 'error', 'message': 'Arduino 重新连接失败'}), 500
        if not current_mode_is_simulation and ser and ser.is_open:
            # 清空缓冲区
            ser.reset_input_buffer()
            
            # 先执行去皮操作
            if data.get('tare_first', False):
                logger.info("强制刷新前执行去皮操作")
                ser.write(b"TARE_SIM\n")
                time.sleep(0.5)  # 等待去皮完成
            
            # 多次尝试获取有效重量
            max_attempts = 3
            for attempt in range(max_attempts):
                # 发送GET_WEIGHT命令
                ser.write(b"GET_WEIGHT\n")
                
                # 等待响应
                response_timeout = 2.0  # 较长的超时时间
                start_time = time.time()
                
                while time.time() - start_time < response_timeout:
                    if ser.in_waiting > 0:
                        line = ser.readline().decode('utf-8', errors='replace').strip()
                        logger.debug(f"强制刷新收到响应: {line}")
                        
                        if line.startswith("WEIGHT:"):
                            try:
                                weight_value = float(line.split(':')[1].strip())
                                
                                # 确认重量是有效值
                                if weight_value >= 0:
                                    with data_lock:
                                        arduino_raw_state["total_weight_in_box_arduino"] = weight_value
                                        arduino_raw_state["last_update"] = time.time()
                                    
                                    # 如果有活动药物，更新库存计算
                                    if pc_active_medication_name and pc_active_medication_name in pc_managed_medication_details:
                                        med_details = pc_managed_medication_details[pc_active_medication_name]
                                        if med_details['wpp'] > 0.001:
                                            med_details['total_weight_in_box'] = weight_value
                                            recalculate_pill_count_for_med(pc_active_medication_name)
                                            logger.info(f"已更新'{pc_active_medication_name}'的库存：{med_details['count_in_box']}片 (总重{weight_value:.3f}g)")
                                    
                                    return jsonify({
                                        'status': 'success',
                                        'weight': weight_value,
                                        'message': f"成功获取实时重量: {weight_value:.3f}g",
                                        'attempt': attempt + 1
                                    })
                            except (ValueError, IndexError) as e:
                                logger.warning(f"解析重量响应失败: {line}, 错误: {e}")
                    
                    time.sleep(0.05)
                
                logger.warning(f"强制刷新重量尝试 {attempt+1}/{max_attempts} 超时")
                time.sleep(0.2)  # 短暂延迟后重试
            
            # 所有尝试都失败
            return jsonify({
                'status': 'error',
                'message': f"无法获取有效重量数据，请检查传感器连接",
                'weight': 0.0
            }), 500
        else:
            # 模拟模式下，直接返回当前模拟重量
            with data_lock:
                weight = arduino_raw_state.get('total_weight_in_box_arduino', 0.0)
            
            return jsonify({
                'status': 'success',
                'weight': weight,
                'message': f"模拟模式下重量: {weight:.3f}g"
            })
    
    except Exception as e:
        error_msg = f"强制刷新重量时发生错误: {str(e)}"
        logger.error(error_msg)
        return jsonify({'status': 'error', 'message': error_msg, 'weight': 0.0}), 500

@app.route('/inventory_setup.html')
def inventory_setup_page():
    """返回库存设置页面"""
    return render_template('inventory_setup.html')

@app.route('/medication_setup.html')
def medication_setup_page():
    """返回药物设置页面(如果不存在则创建一个假页面)"""
    return render_template('inventory_setup.html')  # 临时使用相同页面

if __name__ == '__main__':
    logger.info("Starting Flask Pillbox Controller.")
    if not connect_to_arduino(): 
        logger.warning("Failed to connect to Arduino on startup. The listener thread will keep trying.")
    arduino_thread = threading.Thread(target=read_from_arduino_thread_function, daemon=True)
    arduino_thread.start() 
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
