#include <DFRobot_HX711_I2C.h>
#include <Ultrasonic.h>  // 引入超声波库

// SimulatedPillbox.ino (与V5/V6版本一致)
// 模拟参数和状态
float simulatedWeight = 0.0;       // Arduino当前感应到的总重量 (克)
float weight_per_pill = 0.25;      // 当前选中药物的单片重量 (克)
int pill_count = 0;                // 基于simulatedWeight和weight_per_pill计算出的当前选中药物的数量
bool isSimulationMode = true;      // 默认模拟模式
char selectedMedication[32] = "N/A"; // Arduino当前操作的药物种类，使用字符数组替代String

// 工作阶段定义
enum Stage {
  WEIGHING_STAGE,    // 0: 称重/设置药物阶段
  MEDICATION_STAGE,  // 1: 服药阶段
  RESET_STAGE        // 2: 重置阶段
};
Stage currentStage = WEIGHING_STAGE;
const char* stageNames[] = {"Weighing", "Medication", "Resetting"};

// 串口通信定时
unsigned long lastSerialSendTime = 0;
const long serialSendInterval = 200; // 每200ms发送数据到 PC
// 注意：serialSendInterval 与 weightDisplayInterval 保持一致，以保证整体频率一致

char inputBuffer[64]; // 使用固定大小的缓冲区而不是String
int inputIndex = 0;
boolean stringComplete = false;

// 创建HX711传感器对象
DFRobot_HX711_I2C MyScale;

// 添加测量模式标志
bool isMeasuringMode = false;
unsigned long lastWeightDisplayTime = 0;
const long weightDisplayInterval = 200; // 每200ms更新一次重量显示

// 超声波传感器，使用数字引脚7
Ultrasonic ultrasonic(7);

float boxTareOffset = 0.0; // 箱子重量基准偏移

void setup() {
  Serial.begin(9600);
  
  // 初始化重量传感器
  int sensorInitAttempts = 0;
  while (!MyScale.begin()) {
    Serial.println(F("重量传感器初始化失败，请检查连接"));
    delay(1000);
    sensorInitAttempts++;
    if (sensorInitAttempts > 5) {
      Serial.println(F("无法初始化传感器，将使用模拟模式"));
      isSimulationMode = true;
      break;
    }
  }
  
  // 设置校准值
  MyScale.setCalibration(2236.f);
  
  // 去皮，执行多次以确保稳定
  for (int i = 0; i < 3; i++) {
  MyScale.peel();
    delay(100);
  }
  
  // 测试读取重量，确保传感器正常工作
  if (!isSimulationMode) {
    float testWeight = MyScale.readWeight();
    Serial.print(F("传感器测试读数: "));
    Serial.print(testWeight, 3);
    Serial.println(F(" g"));
  }
  
  Serial.println(F("Arduino Pillbox Ready."));
  Serial.println(isSimulationMode ? F("Mode: Simulation") : F("Mode: Real"));
  Serial.println(F("Waiting for commands from PC..."));
  sendDataToPC(); // 初始发送一次数据
}

void loop() {
  checkSerial(); // 处理串口接收

  if (stringComplete) {
    processCommand(inputBuffer);
    inputIndex = 0;
    inputBuffer[0] = '\0';
    stringComplete = false;
  }

  // 在真实模式下读取实际重量
  if (!isSimulationMode) {
    // 防止传感器读取异常导致断开连接
    float newWeight = MyScale.readWeight();
    // 应用简单的平滑滤波，避免数值跳变
    if (newWeight >= 0 && newWeight < 1000) { // 只接受合理范围内的值
      // 平滑滤波，减少跳变
      simulatedWeight = simulatedWeight * 0.7 + newWeight * 0.3;
    }
    
    // 在测量模式下实时显示重量
    if (isMeasuringMode && (millis() - lastWeightDisplayTime >= weightDisplayInterval)) {
      lastWeightDisplayTime = millis();
      Serial.print(F("当前重量: "));
      Serial.print(simulatedWeight, 3);
      Serial.println(F(" g"));
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
  float rawWeight = 0.0;
  if (!isSimulationMode) {
    rawWeight = MyScale.readWeight();
  } else {
    rawWeight = simulatedWeight;
  }
  float adjustedWeight = rawWeight - boxTareOffset;
  Serial.print(F("DATA:"));
  Serial.print(stageNames[currentStage]); // 当前阶段名称
  Serial.print(F(","));
  Serial.print(adjustedWeight, 2);       // 使用基于BOX_TARE的校正重量
  Serial.print(F(","));
  Serial.print(pill_count);               // 基于 simulatedWeight 和 weight_per_pill 计算出的药丸数量
  Serial.print(F(","));
  Serial.print(selectedMedication);       // Arduino 当前选中的药物
  Serial.print(F(","));
  Serial.print(weight_per_pill, 3);       // Arduino 当前选中药物的单片重量
  // 超声波传感器距离测量
  long lidDistance = ultrasonic.MeasureInCentimeters();
  Serial.print(F(","));
  Serial.print(lidDistance);              // 药盒盖子与传感器距离
  Serial.print(F(","));
  Serial.println(lidDistance > 5 ? 1 : 0); // 距离>5cm表示开启(1)，否则关闭(0)
}

// 检查串口输入
void checkSerial() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    if (inChar == '\n') {
      inputBuffer[inputIndex] = '\0'; // 添加字符串结束符
      stringComplete = true;
      break;
    } else if (inputIndex < sizeof(inputBuffer) - 1) {
      inputBuffer[inputIndex++] = inChar;
    }
  }
}

// 处理命令的辅助函数，检查命令前缀
bool commandStartsWith(const char* cmd, const char* prefix) {
  return strncmp(cmd, prefix, strlen(prefix)) == 0;
}

// 从命令字符串中提取浮点数
float extractFloat(const char* cmd, int startPos) {
  return atof(cmd + startPos);
}

// 从命令字符串中提取整数
int extractInt(const char* cmd, int startPos) {
  return atoi(cmd + startPos);
}

// 从命令字符串中提取文本
void extractText(const char* cmd, int startPos, char* dest, int maxLen) {
  strncpy(dest, cmd + startPos, maxLen - 1);
  dest[maxLen - 1] = '\0'; // 确保字符串结束
}

void processCommand(const char* command) {
  Serial.print(F("Arduino received: ")); Serial.println(command);

  if (commandStartsWith(command, "SET_MODE:")) {
    int mode = extractInt(command, 9);
    isSimulationMode = (mode == 1);
    isMeasuringMode = false; // 切换模式时关闭测量模式
    Serial.print(F("Mode set to: ")); Serial.println(isSimulationMode ? F("Simulation") : F("Real"));
    // 模式改变时，PC端应重新同步活动药物的状态
    simulatedWeight = 0.0; 
    pill_count = 0;
    weight_per_pill = 0.25; 
    strcpy(selectedMedication, "N/A");
    // 在切换到真实模式时重新校准传感器
    if (!isSimulationMode) {
      MyScale.peel();
    }
    Serial.println(F("State reset due to mode change. PC should resync active medication state."));
  } 
  else if (commandStartsWith(command, "SET_STAGE:")) {
    int stageId = extractInt(command, 10);
    if (stageId >= WEIGHING_STAGE && stageId <= RESET_STAGE) {
      currentStage = (Stage)stageId;
      Serial.print(F("Stage changed to: ")); Serial.println(stageNames[currentStage]);
      if (currentStage == RESET_STAGE) {
        simulatedWeight = 0.0;
        pill_count = 0;
        weight_per_pill = 0.25;
        strcpy(selectedMedication, "N/A");
        Serial.println(F("Weight, count, and pill params reset due to RESET_STAGE."));
      }
    }
  } 
  else if (commandStartsWith(command, "SET_PILL_WEIGHT:")) { // 设置当前选中药物的单片重量
    float pillWeightValue = extractFloat(command, 16);
    if (pillWeightValue > 0.0001) {
      weight_per_pill = pillWeightValue;
      Serial.print(F("WPP for '")); Serial.print(selectedMedication); Serial.print(F("' set to: ")); Serial.println(weight_per_pill, 3);
    } else {
      Serial.println(F("Invalid pill weight. Must be > 0.0001"));
    }
  } 
  else if (commandStartsWith(command, "SELECT_MEDICATION:")) { // 设置Arduino当前操作的药物
    extractText(command, 18, selectedMedication, sizeof(selectedMedication));
    Serial.print(F("Arduino active medication context set to: ")); Serial.println(selectedMedication);
    // 重要: PC端在发送此命令后，应紧接着发送 SET_PILL_WEIGHT 和 (模拟模式下) SET_WEIGHT
  }
  // --- 模拟模式专属指令 ---
  else if (isSimulationMode && commandStartsWith(command, "SET_WEIGHT:")) { // 设置Arduino的模拟总重量
    float weightValue = extractFloat(command, 11);
    simulatedWeight = weightValue; 
    Serial.print(F("Arduino simulated total weight (for '")); Serial.print(selectedMedication); Serial.print(F("') set to: ")); Serial.println(simulatedWeight, 2);
  } 
  else if (commandStartsWith(command, "TARE_SIM")) { // 清零Arduino的模拟总重量
    simulatedWeight = 0.0;
    pill_count = 0; // 重量为0，数量也为0
    
    // 在真实模式下，执行传感器的去皮操作
    if (!isSimulationMode) {
      MyScale.peel();
      Serial.println(F("Real mode tare complete. HX711 sensor zeroed."));
    } else {
      Serial.println(F("Simulated tare complete. Arduino total weight and count set to 0."));
    }
  }
  // --- 服药阶段指令 (针对当前选中的药物及其WPP) ---
  else if (currentStage == MEDICATION_STAGE && commandStartsWith(command, "CONSUME_PILLS:")) {
    int numToConsume = extractInt(command, 14);
    if (numToConsume > 0 && weight_per_pill > 0.001 && strcmp(selectedMedication, "N/A") != 0) {
      float weightToReduce = numToConsume * weight_per_pill;
      if (simulatedWeight >= weightToReduce - (weight_per_pill / 2.0) ) { // 允许半片药的误差
        simulatedWeight -= weightToReduce;
        if (simulatedWeight < 0.0001) simulatedWeight = 0.0; // 防止极小的负数或正数残留
        Serial.print(numToConsume); Serial.print(F(" pills of '")); Serial.print(selectedMedication); Serial.println(F("' consumed (Arduino side)."));
        Serial.print(F("Arduino weight reduced by: ")); Serial.print(weightToReduce, 2); Serial.print(F(", new total: ")); Serial.println(simulatedWeight, 2);
      } else {
        Serial.print(F("Not enough '")); Serial.print(selectedMedication); Serial.println(F("' to consume or weight too low on Arduino."));
      }
    } else if (numToConsume <= 0) {
        Serial.println(F("Number of pills to consume must be positive."));
    } else if (strcmp(selectedMedication, "N/A") == 0) {
        Serial.println(F("Cannot consume on Arduino: No medication selected."));
    } else { // WPP 可能为0或未设置
        Serial.println(F("Cannot consume pills on Arduino: WPP not set or is zero for current med."));
    }
  }
  // --- 真实模式下，获取当前重量作为单片药重 (针对当前选中的药物) ---
  else if (!isSimulationMode && commandStartsWith(command, "MEASURE_SINGLE_PILL_WEIGHT")) {
      // 进行多次读取并取平均值，提高稳定性
      float sum = 0.0;
      int validReadings = 0;
      
      // 先发送测量开始的消息
      Serial.println(F("开始测量单片药重，请稍候..."));
      
      // 进行多次测量并取平均值
      for (int i = 0; i < 5; i++) {
        float reading = MyScale.readWeight();
        if (reading >= 0.0001 && reading < 10.0) { // 合理范围内的药片重量
          sum += reading;
          validReadings++;
          Serial.print(F("测量样本 "));
          Serial.print(i+1);
          Serial.print(F(": "));
          Serial.print(reading, 3);
          Serial.println(F("g"));
        }
        delay(100); // 测量间隔，减轻传感器负担
      }
      
      float currentWeight = 0.0;
      if (validReadings > 0) {
        currentWeight = sum / validReadings;
      }
      
      if (currentWeight > 0.0001 && strcmp(selectedMedication, "N/A") != 0) {
          weight_per_pill = currentWeight;
          Serial.print(F("Measured single pill weight for '"));
          Serial.print(selectedMedication);
          Serial.print(F("': "));
          Serial.print(weight_per_pill, 3);
          Serial.println(F("g"));
      } else {
          if (strcmp(selectedMedication, "N/A") == 0) {
              Serial.println(F("Error: No medication selected for measurement"));
          } else {
              Serial.println(F("Error: Measured weight too small or invalid (< 0.0001g)"));
              Serial.print(F("Current reading: "));
              Serial.print(currentWeight, 3);
              Serial.println(F("g"));
          }
      }
      
      isMeasuringMode = false; // 完成测量
  }
  // 添加确认重量命令
  else if (!isSimulationMode && commandStartsWith(command, "CONFIRM_WEIGHT")) {
      float currentWeight = MyScale.readWeight();
      if (currentWeight > 0.0001 && strcmp(selectedMedication, "N/A") != 0) {
          weight_per_pill = currentWeight;
          Serial.print(F("已确认单片药重为: ")); Serial.print(weight_per_pill, 3); Serial.println(F(" g"));
          Serial.print(F("药物: ")); Serial.println(selectedMedication);
          isMeasuringMode = false; // 退出测量模式
      } else {
          Serial.println(F("当前重量无效或未选择药物，请重试"));
      }
  }
  // 添加取消测量命令
  else if (!isSimulationMode && commandStartsWith(command, "CANCEL_MEASURE")) {
      isMeasuringMode = false;
      Serial.println(F("已取消测量"));
  }
  // 添加对GET_WEIGHT命令的处理，直接返回当前重量
  else if (commandStartsWith(command, "GET_WEIGHT")) {
    float currentWeight = 0.0;
    if (isSimulationMode) {
      currentWeight = simulatedWeight;
      Serial.print(F("WEIGHT:"));
      Serial.println(currentWeight, 3);
    } else {
      // 进行多次读取并取平均值，提高稳定性
      float sum = 0.0;
      int validReadings = 0;
      for (int i = 0; i < 5; i++) {  // 增加采样次数
        float reading = MyScale.readWeight();
        if (reading >= 0 && reading < 1000) { // 合理范围内的值
          sum += reading;
          validReadings++;
        }
        delay(10); // 短暂延时，减轻传感器负担
      }
      
      if (validReadings > 0) {
        currentWeight = sum / validReadings;
        // 确保立即发送响应
        Serial.print(F("WEIGHT:"));
        Serial.println(currentWeight, 3);
      } else {
        // 如果没有有效读数，返回0
        Serial.println(F("WEIGHT:0.000"));
        Serial.println(F("Error: No valid weight readings"));
      }
    }
  }
  else if (commandStartsWith(command, "BOX_TARE")) {
      // 记录当前重量作为基准偏移
      boxTareOffset = MyScale.readWeight();
      Serial.println(F("BOX_TARE 完成"));
  }

  sendDataToPC(); // 发送更新后的状态到PC
}
