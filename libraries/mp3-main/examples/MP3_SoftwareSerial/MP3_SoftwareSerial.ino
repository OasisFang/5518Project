#include <MP3_Module.h>
#include <SoftwareSerial.h>

MP3 mp3;

void setup() {
  mp3.begin();

  mp3.volume(30); // Set max volume (1-30)
  mp3.play_track(2); // Play 2nd track
  delay(3000);

  mp3.play_track(1); // Play 1st track
  delay(3000);
  mp3.stop();
}

void loop() {

}