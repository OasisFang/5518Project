# MP3 Module with Speaker

This library is an Arduino library for [YWRobot MP3 Module with Speaker](https://www.kuriosity.sg/mp3-module-with-speaker/) from [www.kuriosity.sg](https://www.kuriosity.sg)

The library uses Software Serial on pins 2 (RX) and 3 (TX) for communication with the MP3 Module. Connect TXD from MP3 Module to pin 2 and RXD from MP3 Module to pin 3 of the Arduino.

## Supported Functions
- void begin();                             // Begin function
- void play();								              // Play
- void pause();								              // Pause
- void stop();                              // Stop track
- void previous();							            // Previous track
- void next();								              // Next track
- void play_track(uint16_t file);				    // Play selected track
- void switch_playback_source(uint8_t src);	// Set playback source (PLAYBACK_USB, PLAYBACK_SD, PLAYBACK_FLASH)
- void volume(uint8_t vol);					        // Set volume (0 - 30)
- void increase_volume();						        // Increase volume by 1
- void decrease_volume();						        // Decrease volume by 1
- void cycle_mode(uint8_t mode);				    // Set cycle mode (WHOLE_DISC_LOOP, SINGLE_LOOP, SINGLE_STOP, ALL_RANDOM, DIRECTORY_LOOP, DIRECTORY_RANDOM, DIRECTORY_ORDER, PLAY_IN_SEQUENCE)
- void loop(uint16_t num);					        // Set number of loops
- void eq(uint8_t eq);						          // Set EQ (NORMAL, POP, ROCK, JAZZ, CLASSIC)
- void playback_channel(uint8_t channel);		// Set playback channel (CHANNEL_MP3, CHANNEL_AUX, CHANNEL_MP3_AUX)
- void total_track_time();					        // Get total track time 
- void enable_track_time_report();			    // Enable report current song time every second
- void disable_track_time_report();			    // Disable report current song time every second

- int get_status();							            // Get current status (0 - STOP, 1 - PLAY, 2 - PAUSE)
- int get_selected_source();					      // Get playback source (0 - USB, 1 - SD, 3 - FLASH)
- int get_playing_source();					        // Get playback source (0 - USB, 1 - SD, 3 - FLASH)
- int get_total_tracks();						        // Get total number of tracks
- int get_current_track();					        // Get current track number

## Documentation
- Full communication protocols: [click here](https://drive.google.com/file/d/1tZgPU4mpxgcl07vuilEHErAAI4f8cuj3/view?usp=sharing)
