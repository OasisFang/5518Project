/*****************************************************************************

	Author  	Kuriosity
	Version 	V1.0

	Copyright www.kuriosity.sg
	All right reserved.

	All text above must be included in any redistribution

*****************************************************************************/

#ifndef MP3_Module_h
#define MP3_Module_h

#if defined(ARDUINO) && ARDUINO >= 100
#include "Arduino.h"
#else
#include "WProgram.h"
#endif
#include "SoftwareSerial.h"

// playback source settings
#define PLAYBACK_USB		0x01
#define PLAYBACK_SD			0x02
#define PLAYBACK_FLASH		0x03

// cycle mode settings
#define WHOLE_DISC_LOOP		0x00 // Play the whole disc in sequence, and play it in a loop after playing
#define SINGLE_LOOP			0x01 // Play the current track in a loop
#define SINGLE_STOP			0x02 // Stop once after playing the current track (DEFAULT)
#define ALL_RANDOM			0x03 // Randomly play the tracks in the drive letter
#define DIRECTORY_LOOP		0x04 // Play the tracks in the current folder in order, and loop after playing, the directory does not contain sub-directories
#define DIRECTORY_RANDOM	0x05 // Play randomly in the current directory, the directory does not contain subdirectories
#define DIRECTORY_ORDER		0x06 // Play the tracks in the current folder in order, stop after playing, the directory does not contain subdirectories
#define PLAY_IN_SEQUENCE	0x07 // Play the entire track in sequence and stop after 

// EQ settings
#define NORMAL				0x00 // Default
#define POP					0x01
#define ROCK				0x02
#define JAZZ				0x03
#define CLASSIC				0x04

// playback channel settings
#define CHANNEL_MP3			0x00 // Default
#define CHANNEL_AUX			0x01
#define CHANNEL_MP3_AUX		0x02

class MP3{
public:
	void begin();								// Begin function
	void play();								// Play
	void pause();								// Pause
	void stop();								// Stop track
	void previous();							// Previous track
	void next();								// Next track
	void play_track(uint16_t file);				// Play selected track
	void switch_playback_source(uint8_t src);	// Set playback source (PLAYBACK_USB, PLAYBACK_SD, PLAYBACK_FLASH)
	void volume(uint8_t vol);					// Set volume (0 - 30)
    void increase_volume();						// Increase volume by 1
	void decrease_volume();						// Decrease volume by 1
    void cycle_mode(uint8_t mode);				// Set cycle mode (WHOLE_DISC_LOOP, SINGLE_LOOP, SINGLE_STOP, ALL_RANDOM, DIRECTORY_LOOP, DIRECTORY_RANDOM, DIRECTORY_ORDER, PLAY_IN_SEQUENCE)
    void loop(uint16_t num);					// Set number of loops
	void eq(uint8_t eq);						// Set EQ (NORMAL, POP, ROCK, JAZZ, CLASSIC)
	void playback_channel(uint8_t channel);		// Set playback channel (CHANNEL_MP3, CHANNEL_AUX, CHANNEL_MP3_AUX)
	void total_track_time();					// Get total track time 
	void enable_track_time_report();			// Enable report current song time every second
	void disable_track_time_report();			// Disable report current song time every second

	int get_status();							// Get current status (0 - STOP, 1 - PLAY, 2 - PAUSE)
	int get_selected_source();					// Get playback source (0 - USB, 1 - SD, 3 - FLASH)
	int get_playing_source();					// Get playback source (0 - USB, 1 - SD, 3 - FLASH)
	int get_total_tracks();						// Get total number of tracks
	int get_current_track();					// Get current track number

private:
	void send_cmd(uint8_t *cmd);				// Send command function

    enum {CMD_BUF_LEN = 10};
    uint8_t cmd_buf[CMD_BUF_LEN];
    uint8_t reply_buf[CMD_BUF_LEN];
};

#endif