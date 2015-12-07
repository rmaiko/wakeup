#!/usr/bin/python
from __future__ import division
import time
import json
import astral
import syslog
import RPi.GPIO as GPIO

OFFSET = 1
    

class Light(object):
    def __init__(self, 
                 gpio_pin           = 17,
                 frequency   	    = 80):
	GPIO.setmode(GPIO.BCM)
	GPIO.setup(gpio_pin, GPIO.OUT)
        self._servo = GPIO.PWM(gpio_pin, frequency)
        self._servo.start(0)
        self._pin   = gpio_pin
        self._freq  = frequency
        self._value = 0
        
    def set(self, value):
    	if self._value == 0 and value > 0:
            self._servo.start(1)
            
        if value <= 0:
            self._servo.stop()
            self._value = 0
            return
        elif value >= 1:
            self._value = 1
            self._servo.ChangeDutyCycle(100)
            self._servo.ChangeFrequency(0.1)
            return
        
        self._servo.ChangeFrequency(self._freq)
        
        # If nothing to do here  
        if self._value == value:
            return
        else:
            self._value = value
        
        # Log perception of light
        value = (10**(value + 1) -1) / 99
        value = value * 100
        self._servo.ChangeDutyCycle(value)
        
    def __del__(self):
        self._servo.stop()
        GPIO.cleanup()
        
class MyTime(object):
    def __init__(self, 
                 lat = 48.1368, 
                 lon = 11.5302, 
                 alt = 529, 
                 tz  = "Berlin"):
        self._astral                    = astral.Astral()
        self._astral.solar_depression   = 'civil'
        self._city                      = self._astral[tz]
        self._city.latitude             = lat
        self._city.longitude            = lon
        self._city.elevation            = alt
        
    def sunrise(self):
        try:
            sun = self._city.sun(local = True)
            sr  = sun["sunrise"]
            retval = sr.hour + sr.minute/60
        except astral.AstralError, _:
            syslog.syslog(syslog.LOG_DEBUG,
                          "No sunrise today, sorry")
            retval = 11
        return retval
    
    def sunset(self):
        try:
            sun = self._city.sun(local = True)
            sr  = sun["sunset"]
            retval = sr.hour + sr.minute/60
        except astral.AstralError, _:
            syslog.syslog(syslog.LOG_INFO,
                          "No sunset today, sorry")
            retval = 13
        return retval
    
    def now(self):
        now = time.localtime()
        return now.tm_hour + now.tm_min / 60
    
    def date(self):
        now = time.localtime()
        return str(now.tm_year * 10000 +
                   now.tm_mon * 100 +
                   now.tm_mday)
        
    def weekday(self):
        now = time.localtime()
        return str(now.tm_wday)
        
class Controller(object):
    def __init__(self, conf = "/etc/wakeup.conf"):
        self._light = Light()
        
        self._fname = conf
        
        self.read_conf_file()
        
        self._time  = MyTime(
                 lat = self._conf["position"]["lat"], 
                 lon = self._conf["position"]["lon"], 
                 alt = self._conf["position"]["alt"], 
                 tz  = self._conf["position"]["tz"]) 
        
        self.time_on  = -1
        self.time_off = -1
        
    def act(self):
        self.define_on_off_times()
        
        time_to_wake    = self.time_on -self._time.now()
        time_to_off     = self.time_off -self._time.now()
        time_to_sunrise = self._time.sunrise() - self._time.now()
        time_to_sunset  = self._time.sunset() - self._time.now()
            
        # Case too late:
        if time_to_off < 0:
            syslog.syslog(syslog.LOG_DEBUG,
                          "Too late to act, bye")
            self._light.set(0)
            return
        
        # Case too early:
        if time_to_wake > OFFSET:
            syslog.syslog(syslog.LOG_DEBUG,
                          "Too early to act, bye")
            self._light.set(0)
            return
        
        # Case sun is still there
        if ((time_to_sunrise < -OFFSET) and 
            (time_to_sunset > OFFSET)):
            syslog.syslog(syslog.LOG_DEBUG,
                          "Sun is there, bye")
            self._light.set(0)
            return
            
        # Case we should be awake (morning)
        if ((time_to_wake < 0) and
            (time_to_sunrise > OFFSET)):
            syslog.syslog(syslog.LOG_DEBUG,
                          "Sun should be there, good morning")
            self._light.set(1)
            return
            
        # Case we should be awake (night)
        if ((time_to_sunset < 0) and
            (time_to_off > OFFSET)):
            syslog.syslog(syslog.LOG_DEBUG,
                          "Sun should be there, still awake")
            self._light.set(1)
            return
        
        # Case waking up:
        if ((time_to_wake <= OFFSET)
            and
            (time_to_wake >= 0)):
            syslog.syslog(syslog.LOG_DEBUG,
                          "Waking up in " +
                          str(time_to_wake)
                          + " hours")
            self._light.set(1 - time_to_wake / OFFSET)
            return
        
        # Case turning off at morning
        if ((time_to_sunrise < 0) and
            (time_to_sunrise + OFFSET > 0)):
            syslog.syslog(syslog.LOG_DEBUG,
                          "Shutting off, have a nice day")
            self._light.set(-time_to_sunrise / OFFSET)
            return
        
        # Case turning on at night
        if ((time_to_sunset < OFFSET) and
            (time_to_sunset > 0)):
            syslog.syslog(syslog.LOG_DEBUG,
                          "Turning on to compensate lack of light")
            self._light.set(1 - time_to_sunset / OFFSET)
            return        
        
        # Case turning off at night
        if ((time_to_off < OFFSET) and
            (time_to_off > 0)):
            syslog.syslog(syslog.LOG_DEBUG,
                          "Shutting off, good night")
            self._light.set(time_to_off / OFFSET)
            return
            

        
    def define_on_off_times(self):
        self.read_conf_file()
        # General case
        self.time_on  = self._conf["general"]["on"]
        self.time_off = self._conf["general"]["off"]
        syslog.syslog(syslog.LOG_DEBUG,
                      "Got from general config: ")
        
        # Weekday case
        if self._time.weekday() in self._conf:
            self.time_on  = self._conf[self._time.weekday()]["on"]
            self.time_off = self._conf[self._time.weekday()]["off"]
            syslog.syslog(syslog.LOG_DEBUG,
                          "Got from weekday config: ")
            
        # Specific date case
        if self._time.date() in self._conf:
            self.time_on  = self._conf[self._time.date()]["on"]
            self.time_off = self._conf[self._time.date()]["off"]
            syslog.syslog(syslog.LOG_DEBUG, 
                          "Got from specific day config: ")

        syslog.syslog(syslog.LOG_DEBUG, 
                      "ONTIME:  " + str(self.time_on))
        syslog.syslog(syslog.LOG_DEBUG, 
                      "OFFTIME: " + str(self.time_off))
            
    def read_conf_file(self):   
        try:
            f = open(self._fname, "r")
            j = f.read()
            f.close()              
            self._conf = json.loads(j)
        except:
            syslog.syslog(syslog.LOG_CRIT,
                "Failed reading conf file. Using old conf.")
        

if __name__ == "__main__":
#    syslog.setlogmask(syslog.LOG_DEBUG)
    syslog.syslog(syslog.LOG_INFO,
                "Process wakeup started")
    time.sleep(3)
    c = Controller()
#    s = c._time
#    print("Sunrise: ", s.sunrise())
#    print("Sunset:  ", s.sunset())
#    print("Today:   ", s.date())
    while True:
        c.act()
        time.sleep(300)
