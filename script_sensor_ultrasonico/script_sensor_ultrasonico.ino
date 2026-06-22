#include <HCSR04.h>

UltraSonicDistanceSensor distanceSensor(13, 12);  // Initialize sensor that uses digital pins 13 and 12.

void setup() {
  Serial.begin(9600);
}

void loop() {
  Serial.println(distanceSensor.measureDistanceCm());

  delay(1000);
}