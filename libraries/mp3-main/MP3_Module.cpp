/*****************************************************************************

	Author  	Kuriosity
	Version 	V1.0

	Copyright www.kuriosity.sg
	All right reserved.

	All text above must be included in any redistribution

*****************************************************************************/

#include "MP3_Module.h"

SoftwareSerial COM_SOFT(2, 3);

void MP3::begin()
{
	COM_SOFT.begin(9600);
	delay(10);
}

void MP3::send_cmd(uint8_t *cmd)
{
	uint8_t i;
	uint8_t length;
	uint8_t checksum;

	length = cmd[2] + 4;
	if (length > 10) {
		return;
	}

	cmd[0] = 0xAA;
	for (i = 0; i < length - 1; i++) {
		checksum += cmd[i];
	}
	cmd[length - 1] = checksum;
	
	for (i = 0; i < length; i++){
		COM_SOFT.write(cmd[i]);
	}
}

int MP3::get_status()
{
	while(COM_SOFT.available()) COM_SOFT.read();

	uint8_t i = 0;
	uint8_t length = 0;
	uint8_t checksum = 0;
	
	cmd_buf[1] = 0x01;
	cmd_buf[2] = 0x00;
	send_cmd(cmd_buf);
	
	if (COM_SOFT.available()) {
		while (COM_SOFT.available()) {
			char c = COM_SOFT.read();
			reply_buf[length++] = c;
			delay(2);
		}
	}

	for (i = 0; i < length - 1; i++) {
		checksum += reply_buf[i];
	}
	if (reply_buf[length - 1] == checksum) {
		return reply_buf[3];
	}
	
	return -1;
}

void MP3::play()
{
	cmd_buf[1] = 0x02;
	cmd_buf[2] = 0x00;
	send_cmd(cmd_buf);
}

void MP3::pause()
{
	cmd_buf[1] = 0x03;
	cmd_buf[2] = 0x00;
	send_cmd(cmd_buf);
}

void MP3::stop()
{
	cmd_buf[1]=0x04;
	cmd_buf[2]=0x00;
	send_cmd(cmd_buf);
}

void MP3::previous()
{
	cmd_buf[1] = 0x05;
	cmd_buf[2] = 0x00;
	send_cmd(cmd_buf);
}

void MP3::next()
{
	cmd_buf[1] = 0x06;
	cmd_buf[2] = 0x00;
	send_cmd(cmd_buf);
}

void MP3::play_track(uint16_t file)
{
	cmd_buf[1] = 0x07;
	cmd_buf[2] = 0x02;
	cmd_buf[3] = (uint8_t)(file >> 8);
	cmd_buf[4] = (uint8_t)file;
	send_cmd(cmd_buf);
}

int MP3::get_selected_source()
{
	while(COM_SOFT.available()) COM_SOFT.read();

	uint8_t i = 0;
	uint8_t length = 0;
	uint8_t checksum = 0;
	
	cmd_buf[1] = 0x09;
	cmd_buf[2] = 0x00;
	send_cmd(cmd_buf);
	
	if (COM_SOFT.available()) {
		while (COM_SOFT.available()) {
			char c = COM_SOFT.read();
			reply_buf[length++] = c;
			delay(2);
		}
	}

	for (i = 0; i < length - 1; i++) {
		checksum += reply_buf[i];
	}
	if (reply_buf[length - 1] == checksum) {
		return reply_buf[3];
	}
	
	return -1;
}

int MP3::get_playing_source()
{
	while(COM_SOFT.available()) COM_SOFT.read();

	uint8_t i = 0;
	uint8_t length = 0;
	uint8_t checksum = 0;
	
	cmd_buf[1] = 0x0A;
	cmd_buf[2] = 0x00;
	send_cmd(cmd_buf);
	
	if (COM_SOFT.available()) {
		while (COM_SOFT.available()) {
			char c = COM_SOFT.read();
			reply_buf[length++] = c;
			delay(2);
		}
	}

	for (i = 0; i < length - 1; i++) {
		checksum += reply_buf[i];
	}
	if (reply_buf[length - 1] == checksum) {
		return reply_buf[3];
	}
	
	return -1;
}

void MP3::switch_playback_source(uint8_t src)
{
	cmd_buf[1] = 0x0B;
	cmd_buf[2] = 0x01;
	cmd_buf[3] = src;
	send_cmd(cmd_buf);
}

int MP3::get_total_tracks()
{
	while(COM_SOFT.available()) COM_SOFT.read();

	uint8_t i = 0;
	uint8_t length = 0;
	uint8_t checksum = 0;
	
	cmd_buf[1] = 0x0C;
	cmd_buf[2] = 0x00;
	send_cmd(cmd_buf);
	
	if (COM_SOFT.available()) {
		while (COM_SOFT.available()) {
			char c = COM_SOFT.read();
			reply_buf[length++] = c;	
			delay(2);
		}
	}

	for (i = 0; i < length - 1; i++) {
		checksum += reply_buf[i];
	}

	if (reply_buf[length - 1] == checksum) {
		return (reply_buf[3] << 8) | reply_buf[4];
	}
	
	return -1;
}

int MP3::get_current_track()
{
	while(COM_SOFT.available()) COM_SOFT.read();

	uint8_t i = 0;
	uint8_t length = 0;
	uint8_t checksum = 0;
	
	cmd_buf[1] = 0x0D;
	cmd_buf[2] = 0x00;
	send_cmd(cmd_buf);
	
	if (COM_SOFT.available()) {
		while (COM_SOFT.available()) {
			char c = COM_SOFT.read();
			reply_buf[length++] = c;	
			delay(2);
		}
	}

	for (i = 0; i < length - 1; i++) {
		checksum += reply_buf[i];
	}

	if (reply_buf[length - 1] == checksum) {
		return (reply_buf[3] << 8) | reply_buf[4];
	}
	
	return -1;
}

void MP3::volume(uint8_t vol)
{
	cmd_buf[1] = 0x13;
	cmd_buf[2] = 0x01;
	cmd_buf[3] = vol;
	send_cmd(cmd_buf);
}

void MP3::increase_volume()
{
	cmd_buf[1] = 0x14;
	cmd_buf[2] = 0x00;
	send_cmd(cmd_buf);
}

void MP3::decrease_volume()
{
	cmd_buf[1] = 0x15;
	cmd_buf[2] = 0x00;
	send_cmd(cmd_buf);
}

void MP3::cycle_mode(uint8_t mode)
{
	cmd_buf[1] = 0x18;
	cmd_buf[2] = 0x01;
	cmd_buf[3] = mode;
	send_cmd(cmd_buf);
}

void MP3::loop(uint16_t num)
{
	cmd_buf[1] = 0x19;
	cmd_buf[2] = 0x02;
	cmd_buf[3] = (uint8_t)(num >> 8);
	cmd_buf[4] = (uint8_t)num;
	send_cmd(cmd_buf);
}

void MP3::eq(uint8_t mode)
{
	cmd_buf[1] = 0x1A;
	cmd_buf[2] = 0x01;
	cmd_buf[3] = mode;
	send_cmd(cmd_buf);
}

void MP3::playback_channel(uint8_t channel)
{
	cmd_buf[1] = 0x1D;
	cmd_buf[2] = 0x01;
	cmd_buf[3] = channel;
	send_cmd(cmd_buf);
}

void MP3::total_track_time()
{
	cmd_buf[1] = 0x24;
	cmd_buf[2] = 0x00;
	send_cmd(cmd_buf);
}

void MP3::enable_track_time_report()
{
	cmd_buf[1] = 0x25;
	cmd_buf[2] = 0x00;
	send_cmd(cmd_buf);	
}

void MP3::disable_track_time_report()
{
	cmd_buf[1] = 0x26;
	cmd_buf[2] = 0x00;
	send_cmd(cmd_buf);	
}