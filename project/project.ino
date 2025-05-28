#include <DFRobot_HX711_I2C.h>
#include <Ultrasonic.h>  // Include ultrasonic library
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

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

// Initialize I2C LCD (address 0x27, 16 columns, 2 rows)
LiquidCrystal_I2C lcd(0x27, 16, 2);

// Reminder timing variables
unsigned long remindStartTime = 0;    // millis when reminder starts
unsigned long missedStartTime = 0;    // millis when missed reminder starts
bool showMissed = false;              // flag indicating missed display
// Next medication time display
char nextMedicationTime[6] = "";      // HH:MM format or current time
bool hasNextTime = false;             // flag indicating next medication time is set

void setup() {
  Serial.begin(9600);
  
  // Initialize I2C LCD
  lcd.init();
  lcd.backlight();
  
  // Display default message
  lcd.clear();
  lcd.setCursor(0,0);
  lcd.print("PharmaPlan");
  
  // Initialize weight sensor
  int sensorInitAttempts = 0;
  while (!MyScale.begin()) {
    Serial.println(F("Weight sensor initialization failed, please check connection"));
    delay(1000);
    sensorInitAttempts++;
    if (sensorInitAttempts > 5) {
      Serial.println(F("Unable to initialize sensor, switching to simulation mode"));
      isSimulationMode = true;
      break;
    }
  }
  
  // Set calibration value
  MyScale.setCalibration(2236.f);
  
  // Tare, execute multiple times to ensure stability
  for (int i = 0; i < 3; i++) {
    MyScale.peel();
    delay(100);
  }
  
  // Test weight reading to ensure sensor is working
  if (!isSimulationMode) {
    float testWeight = MyScale.readWeight();
    Serial.print(F("Sensor test reading: "));
    Serial.print(testWeight, 3);
    Serial.println(F(" g"));
  }
  
  Serial.println(F("Arduino Pillbox Ready."));
  Serial.println(isSimulationMode ? F("Mode: Simulation") : F("Mode: Real"));
  Serial.println(F("Waiting for commands from PC..."));
  sendDataToPC(); // Initial data send to PC
}

void loop() {
  checkSerial(); // Process serial input

  if (stringComplete) {
    processCommand(inputBuffer);
    inputIndex = 0;
    inputBuffer[0] = '\0';
    stringComplete = false;
  }

  // Read actual weight in real mode
  if (!isSimulationMode) {
    // Prevent sensor reading anomalies from causing disconnection
    float newWeight = MyScale.readWeight();
    // Apply simple smoothing filter to avoid value jumps
    if (newWeight >= 0 && newWeight < 1000) { // Only accept values within reasonable range
      // Smoothing filter to reduce jumps
      simulatedWeight = simulatedWeight * 0.7 + newWeight * 0.3;
    }
    
    // Display weight in real-time during measurement mode
    if (isMeasuringMode && (millis() - lastWeightDisplayTime >= weightDisplayInterval)) {
      lastWeightDisplayTime = millis();
      Serial.print(F("Current weight: "));
      Serial.print(simulatedWeight, 3);
      Serial.println(F(" g"));
    }
  }

  // Calculate pill count based on current pillbox total weight (simulatedWeight) and current pill weight (weight_per_pill)
  if (weight_per_pill > 0.001) {
    if (simulatedWeight < (weight_per_pill / 2.0)) { // If total weight is less than half a pill, consider it empty
      pill_count = 0;
    } else {
      // Round to calculate pill count
      pill_count = round(simulatedWeight / weight_per_pill);
    }
  } else {
    pill_count = 0; // If single pill weight is not set or zero, pill count is zero
  }

  // Periodically send current status to PC
  if (millis() - lastSerialSendTime >= serialSendInterval) {
    lastSerialSendTime = millis();
    sendDataToPC();
  }
  delay(10); // Short delay to keep loop stable

  // Update LCD display based on reminder timers
  unsigned long now = millis();
  // Transition to missed state if reminder expired
  if (remindStartTime > 0 && now - remindStartTime > 1800000UL) {
    if (!showMissed) {
      showMissed = true;
      missedStartTime = now;
      lcd.clear();
      lcd.setCursor(0,0);
      lcd.print("Missed");
      lcd.setCursor(0,1);
      lcd.print("medication");
    }
  }
  // Return to default after missed period
  if (showMissed && now - missedStartTime > 1800000UL) {
    showMissed = false;
    lcd.clear();
    lcd.setCursor(0,0);
    lcd.print("PharmaPlan");
  }
  // Default display under PharmaPlan: next medication time or current time
  if (remindStartTime == 0 && !showMissed) {
    lcd.setCursor(0,1);
    if (hasNextTime) {
      lcd.print("Next: ");
      lcd.print(nextMedicationTime);
    } else {
      lcd.print(nextMedicationTime);
    }
  }
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
  Serial.print(stageNames[currentStage]); // Current stage name
  Serial.print(F(","));
  Serial.print(adjustedWeight, 2);       // Weight corrected based on BOX_TARE
  Serial.print(F(","));
  Serial.print(pill_count);               // Pill count based on simulatedWeight and weight_per_pill
  Serial.print(F(","));
  Serial.print(selectedMedication);       // Current selected medication on Arduino
  Serial.print(F(","));
  Serial.print(weight_per_pill, 3);       // Single pill weight of current selected medication on Arduino
  // Ultrasonic sensor distance measurement
  long lidDistance = ultrasonic.MeasureInCentimeters();
  Serial.print(F(","));
  Serial.print(lidDistance);              // Distance between pillbox lid and sensor
  Serial.print(F(","));
  Serial.println(lidDistance > 5 ? 1 : 0); // Distance > 5cm indicates open (1), otherwise closed (0)
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
      // Perform multiple readings and take average for stability
      float sum = 0.0;
      int validReadings = 0;
      
      // First send measurement start message
      Serial.println(F("Starting single pill weight measurement, please wait..."));
      
      // Perform multiple measurements and take average
      for (int i = 0; i < 5; i++) {
        float reading = MyScale.readWeight();
        if (reading >= 0.0001 && reading < 10.0) { // Reasonable pill weight range
          sum += reading;
          validReadings++;
          Serial.print(F("Measurement sample "));
          Serial.print(i+1);
          Serial.print(F(": "));
          Serial.print(reading, 3);
          Serial.println(F("g"));
        }
        delay(100); // Measurement interval to reduce sensor load
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
          Serial.print(F("Confirmed single pill weight: ")); Serial.print(weight_per_pill, 3); Serial.println(F(" g"));
          Serial.print(F("Medication: ")); Serial.println(selectedMedication);
          isMeasuringMode = false; // Exit measurement mode
      } else {
          Serial.println(F("Current weight invalid or no medication selected, please try again"));
      }
  }
  // 添加取消测量命令
  else if (!isSimulationMode && commandStartsWith(command, "CANCEL_MEASURE")) {
      isMeasuringMode = false;
      Serial.println(F("Measurement cancelled"));
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
      Serial.println(F("BOX_TARE complete"));
  }
  else if (commandStartsWith(command, "LCD:REMIND")) {
    // Start reminder: half-hour before medication
    remindStartTime = millis();
    showMissed = false;
    lcd.clear();
    lcd.setCursor(0,0);
    lcd.print("Time to take");
    lcd.setCursor(0,1);
    lcd.print("medication");
  }
  else if (commandStartsWith(command, "LCD:TAKEN")) {
    // Medication taken: reset display
    remindStartTime = 0;
    showMissed = false;
    lcd.clear();
    lcd.setCursor(0,0);
    lcd.print("PharmaPlan");
  }
  else if (commandStartsWith(command, "LCD:NEXT:")) {
    // Receive next medication time in HH:MM
    extractText(command, 9, nextMedicationTime, sizeof(nextMedicationTime));
    hasNextTime = true;
    lcd.clear();
    lcd.setCursor(0,0);
    lcd.print("PharmaPlan");
    lcd.setCursor(0,1);
    lcd.print("Next: "); lcd.print(nextMedicationTime);
  }
  else if (commandStartsWith(command, "LCD:TIME:")) {
    // Receive current time when no medication scheduled
    extractText(command, 9, nextMedicationTime, sizeof(nextMedicationTime));
    hasNextTime = false;
    lcd.clear();
    lcd.setCursor(0,0);
    lcd.print("PharmaPlan");
    lcd.setCursor(0,1);
    lcd.print(nextMedicationTime);
  }

  sendDataToPC(); // 发送更新后的状态到PC
}
