 
    #include <SoftwareSerial.h>

    SoftwareSerial Serial1(10, 11);//10连接模块TX，11连接模块RX

    unsigned char order[4] = {0xAA,0x06,0x00,0xB0};


    void setup() {
    //Serial.begin(115200);
     Serial1.begin(9600);
     volume(0x06);//音量设置0x00-0x1E
    }

    void loop() {

     play(0x02);//指定播放:0x01-文件0001
    // Serial1.write(order,4);//顺序播放
     delay(3000);

    }

    void play(unsigned char Track)
    {
     unsigned char play[6] = {0xAA,0x07,0x02,0x00,Track,Track+0xB3};//0xB3=0xAA+0x07+0x02+0x00,即最后一位为校验和
       Serial1.write(play,6);
    }
    void volume( unsigned char vol)
    {
      unsigned char volume[5] = {0xAA,0x13,0x01,vol,vol+0xBE};//0xBE=0xAA+0x13+0x01,即最后一位为校验和
         Serial1.write(volume,5);
     }
