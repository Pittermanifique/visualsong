#include <M5Unified.h>

void setup() {
  // Initialize M5Stack
  M5.begin();

  // Initialize the display
  M5.Lcd.begin();
  // Set up other components or configurations as needed
  M5.Lcd.setTextSize(2);
  M5.Lcd.println("M5Stack Initialized");

  Serial.begin(115200);
}

void loop() {
  if (Serial.available() > 0) {
    String ligne = Serial.readStringUntil('\n');
    if (ligne == "1") {
      M5.Lcd.clear();
      M5.Lcd.drawCircle(120, 120, 50, TFT_GREEN);
    } else if(ligne == "0") {
      M5.Lcd.clear();
    }
  }
}

