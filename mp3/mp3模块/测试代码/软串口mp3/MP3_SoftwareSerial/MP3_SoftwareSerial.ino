#include <SoftwareSerial.h>

SoftwareSerial mySerial(10, 11);//10连接模块TX，11连接模块RX
unsigned char order[4] = {0xAA, 0x06, 0x00, 0xB0};


void setup() {
  mySerial.begin(9600);
  Serial.begin(9600);
  volume(0x0F);//音量设置0x00-0x1E，下面是1-30级音量对应的参数
  //--1-----2-----3-----4-----5-----6-----7-----8-----9----10----11----12----13----14----15--
  //0x01--0x02--0x03--0x04--0x05--0x06--0x07--0x08--0x09--0x0A--0x0B--0x0C--0x0D--0x0E--0x0F-
  //-16----17----18----19----20----21----22----23----24----25----26----27----28----29----30--
  //0x10--0x11--0x12--0x13--0x14--0x15--0x16--0x17--0x18--0x19--0x1A--0x1B--0x1C--0x1D--0x1E-
}

void loop() {
  play(0x01);
  delay(3000);
  play(0x02);
  delay(3000);
}

void play(unsigned char Track) {  //序列播放，顺序由文件拷贝进内存的顺序而定，和文件名无关
  unsigned char play[6] = {0xAA, 0x07, 0x02, 0x00, Track, Track + 0xB3}; //0xB3=0xAA+0x07+0x02+0x00,即最后一位为校验和
  mySerial.write(play, 6);
}

void volume(unsigned char vol) {
  unsigned char volume[5] = {0xAA, 0x13, 0x01, vol, vol + 0xBE}; //0xBE=0xAA+0x13+0x01,即最后一位为校验和
  mySerial.write(volume, 5);
}
