#include <DFRobot_HX711_I2C.h>

// SimulatedPillbox.ino (与V5/V6版本一致)
// 模拟参数和状态
float simulatedWeight = 0.0;       // Arduino当前感应到的总重量 (克)
float weight_per_pill = 0.25;      // 当前选中药物的单片重量 (克)
int pill_count = 0;                // 基于simulatedWeight和weight_per_pill计算出的当前选中药物的数量
bool isSimulationMode = true;      // 默认模拟模式
String selectedMedication = "N/A"; // Arduino当前操作的药物种类

// 工作阶段定义
enum Stage {
  WEIGHING_STAGE,    // 0: 称重/设置药物阶段
  MEDICATION_STAGE,  // 1: 服药阶段
  RESET_STAGE        // 2: 重置阶段
};
Stage currentStage = WEIGHING_STAGE;
String stageNames[] = {"Weighing", "Medication", "Resetting"};

// 串口通信定时
unsigned long lastSerialSendTime = 0;
const long serialSendInterval = 1000; // 每秒发送数据到 PC

String inputString = "";
boolean stringComplete = false;

// 创建HX711传感器对象
DFRobot_HX711_I2C MyScale;

// 添加测量模式标志
bool isMeasuringMode = false;
unsigned long lastWeightDisplayTime = 0;
const long weightDisplayInterval = 200; // 每200ms更新一次重量显示

void setup() {
  Serial.begin(9600);
  inputString.reserve(200);
  
  // 初始化重量传感器
  while (!MyScale.begin()) {
    Serial.println("重量传感器初始化失败，请检查连接");
    delay(1000);
  }
  // 设置校准值
  MyScale.setCalibration(2236.f);
  // 去皮
  MyScale.peel();
  
  Serial.println("Arduino Pillbox Ready.");
  Serial.println(isSimulationMode ? "Mode: Simulation" : "Mode: Real");
  Serial.println("Waiting for commands from PC...");
  sendDataToPC(); // 初始发送一次数据
}

void loop() {
  serialEvent(); // 处理串口接收

  if (stringComplete) {
    processCommand(inputString);
    inputString = "";
    stringComplete = false;
  }

  // 在真实模式下读取实际重量
  if (!isSimulationMode) {
    simulatedWeight = MyScale.readWeight();
    
    // 在测量模式下实时显示重量
    if (isMeasuringMode && (millis() - lastWeightDisplayTime >= weightDisplayInterval)) {
      lastWeightDisplayTime = millis();
      Serial.print("当前重量: ");
      Serial.print(simulatedWeight, 2);
      Serial.println(" g");
    }
  }

  // 根据当前药盒总重量(simulatedWeight)和当前药物的单片药重(weight_per_pill)计算数量
  if (weight_per_pill > 0.001) {
    if (simulatedWeight < (weight_per_pill / 2.0)) { // 如果总重不足半片，则认为没有药
      pill_count = 0;
    } else {
      // 四舍五入计算药丸数量
      pill_count = round(simulatedWeight / weight_per_pill);
    }
  } else {
    pill_count = 0; // 如果单片药重未设置或为零，则药丸数量为零
  }

  // 定期发送当前状态到 PC
  if (millis() - lastSerialSendTime >= serialSendInterval) {
    lastSerialSendTime = millis();
    sendDataToPC();
  }
  delay(10); // 短暂延时，保持循环稳定
}

void sendDataToPC() {
  Serial.print("DATA:");
  Serial.print(stageNames[currentStage]); // 当前阶段名称
  Serial.print(",");
  Serial.print(simulatedWeight, 2);       // Arduino 当前的模拟总重量
  Serial.print(",");
  Serial.print(pill_count);               // 基于 simulatedWeight 和 weight_per_pill 计算出的药丸数量
  Serial.print(",");
  Serial.print(selectedMedication);       // Arduino 当前选中的药物
  Serial.print(",");
  Serial.println(weight_per_pill, 3);     // Arduino 当前选中药物的单片重量
}

void processCommand(String command) {
  Serial.print("Arduino received: "); Serial.println(command);

  if (command.startsWith("SET_MODE:")) {
    int mode = command.substring(9).toInt();
    isSimulationMode = (mode == 1);
    isMeasuringMode = false; // 切换模式时关闭测量模式
    Serial.print("Mode set to: "); Serial.println(isSimulationMode ? "Simulation" : "Real");
    // 模式改变时，PC端应重新同步活动药物的状态
    simulatedWeight = 0.0; 
    pill_count = 0;
    weight_per_pill = 0.25; 
    selectedMedication = "N/A"; 
    // 在切换到真实模式时重新校准传感器
    if (!isSimulationMode) {
      MyScale.peel();
    }
    Serial.println("State reset due to mode change. PC should resync active medication state.");
  } else if (command.startsWith("SET_STAGE:")) {
    int stageId = command.substring(10).toInt();
    if (stageId >= WEIGHING_STAGE && stageId <= RESET_STAGE) {
      currentStage = (Stage)stageId;
      Serial.print("Stage changed to: "); Serial.println(stageNames[currentStage]);
      if (currentStage == RESET_STAGE) {
        simulatedWeight = 0.0;
        pill_count = 0;
        weight_per_pill = 0.25;
        selectedMedication = "N/A";
        Serial.println("Weight, count, and pill params reset due to RESET_STAGE.");
      }
    }
  } else if (command.startsWith("SET_PILL_WEIGHT:")) { // 设置当前选中药物的单片重量
    float pillWeightValue = command.substring(16).toFloat();
    if (pillWeightValue > 0.0001) {
      weight_per_pill = pillWeightValue;
      Serial.print("WPP for '");Serial.print(selectedMedication);Serial.print("' set to: "); Serial.println(weight_per_pill, 3);
    } else {
      Serial.println("Invalid pill weight. Must be > 0.0001");
    }
  } else if (command.startsWith("SELECT_MEDICATION:")) { // 设置Arduino当前操作的药物
    selectedMedication = command.substring(18);
    Serial.print("Arduino active medication context set to: "); Serial.println(selectedMedication);
    // 重要: PC端在发送此命令后，应紧接着发送 SET_PILL_WEIGHT 和 (模拟模式下) SET_WEIGHT
  }
  // --- 模拟模式专属指令 ---
  else if (isSimulationMode && command.startsWith("SET_WEIGHT:")) { // 设置Arduino的模拟总重量
    float weightValue = command.substring(11).toFloat();
    simulatedWeight = weightValue; 
    Serial.print("Arduino simulated total weight (for '"); Serial.print(selectedMedication); Serial.print("') set to: "); Serial.println(simulatedWeight, 2);
  } else if (isSimulationMode && command.startsWith("TARE_SIM")) { // 清零Arduino的模拟总重量
    simulatedWeight = 0.0;
    pill_count = 0; // 重量为0，数量也为0
    Serial.println("Simulated tare complete. Arduino total weight and count set to 0.");
  }
  // --- 服药阶段指令 (针对当前选中的药物及其WPP) ---
  else if (currentStage == MEDICATION_STAGE && command.startsWith("CONSUME_PILLS:")) {
    int numToConsume = command.substring(14).toInt();
    if (numToConsume > 0 && weight_per_pill > 0.001 && selectedMedication != "N/A") {
      float weightToReduce = numToConsume * weight_per_pill;
      if (simulatedWeight >= weightToReduce - (weight_per_pill / 2.0) ) { // 允许半片药的误差
        simulatedWeight -= weightToReduce;
        if (simulatedWeight < 0.0001) simulatedWeight = 0.0; // 防止极小的负数或正数残留
        Serial.print(numToConsume); Serial.print(" pills of '"); Serial.print(selectedMedication); Serial.println("' consumed (Arduino side).");
        Serial.print("Arduino weight reduced by: "); Serial.print(weightToReduce, 2); Serial.print(", new total: "); Serial.println(simulatedWeight, 2);
      } else {
        Serial.print("Not enough '"); Serial.print(selectedMedication); Serial.println("' to consume or weight too low on Arduino.");
      }
    } else if (numToConsume <= 0) {
        Serial.println("Number of pills to consume must be positive.");
    } else if (selectedMedication == "N/A") {
        Serial.println("Cannot consume on Arduino: No medication selected.");
    } else { // WPP 可能为0或未设置
        Serial.println("Cannot consume pills on Arduino: WPP not set or is zero for current med.");
    }
  }
  // --- 真实模式下，获取当前重量作为单片药重 (针对当前选中的药物) ---
  else if (!isSimulationMode && command.startsWith("MEASURE_SINGLE_PILL_WEIGHT")) {
      isMeasuringMode = true; // 进入测量模式
      Serial.println("开始测量单片药重...");
      Serial.println("请将一片药放入药盒，等待重量稳定后输入'CONFIRM_WEIGHT'确认当前重量");
      Serial.println("或输入'CANCEL_MEASURE'取消测量");
  }
  // 添加确认重量命令
  else if (!isSimulationMode && command.startsWith("CONFIRM_WEIGHT")) {
      float currentWeight = MyScale.readWeight();
      if (currentWeight > 0.0001 && selectedMedication != "N/A") {
          weight_per_pill = currentWeight;
          Serial.print("已确认单片药重为: "); Serial.print(weight_per_pill, 3); Serial.println(" g");
          Serial.print("药物: "); Serial.println(selectedMedication);
          isMeasuringMode = false; // 退出测量模式
      } else {
          Serial.println("当前重量无效或未选择药物，请重试");
      }
  }
  // 添加取消测量命令
  else if (!isSimulationMode && command.startsWith("CANCEL_MEASURE")) {
      isMeasuringMode = false;
      Serial.println("已取消测量");
  }

  sendDataToPC(); // 发送更新后的状态到PC
}

void serialEvent() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    if (inChar == '\n') {
      inputString.trim(); // 去除首尾空白
      stringComplete = true;
    } else {
      inputString += inChar;
    }
  }
}
